"""
Service for exporting trips to various formats (PDF, ICS, GPX, JSON)
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.models.schemas import TripData, ExportFormat, Place
import json
import logging

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting trip data"""
    
    def export_trip(
        self,
        trip_data: TripData,
        format: ExportFormat,
        include_photos: bool = False
    ) -> str:
        """
        Экспортировать маршрут в указанный формат
        
        Args:
            trip_data: Данные маршрута
            format: Формат экспорта
            include_photos: Включить фото
            
        Returns:
            Строка с экспортированными данными
        """
        if format == ExportFormat.JSON:
            return self._export_json(trip_data, include_photos)
        elif format == ExportFormat.ICS:
            return self._export_ics(trip_data)
        elif format == ExportFormat.GPX:
            return self._export_gpx(trip_data)
        elif format == ExportFormat.PDF:
            # PDF требует дополнительных библиотек
            raise NotImplementedError("PDF export requires additional setup")
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _export_json(self, trip_data: TripData, include_photos: bool) -> str:
        """
        Экспорт в JSON
        
        Args:
            trip_data: Данные маршрута
            include_photos: Включить фото
            
        Returns:
            JSON строка
        """
        data = trip_data.model_dump()
        
        if not include_photos:
            # Удалить фото для уменьшения размера
            data["photos"] = []
            for stop in data.get("stops", []):
                stop["photos"] = []
                stop["user_photos"] = []
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def _export_ics(self, trip_data: TripData) -> str:
        """
        Экспорт в ICS (iCalendar) формат для календарей
        
        Args:
            trip_data: Данные маршрута
            
        Returns:
            ICS строка
        """
        # Базовая структура ICS
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//TravelPath//Trip Planner//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        
        # Создать событие для каждого временного слота
        for time_slot in trip_data.time_slots:
            # Парсить время
            start_time = datetime.strptime(time_slot.start_time, "%H:%M")
            end_time = datetime.strptime(time_slot.end_time, "%H:%M")
            
            # Использовать дату создания маршрута
            try:
                trip_date = datetime.fromisoformat(trip_data.created_at.replace('Z', '+00:00'))
            except:
                trip_date = datetime.now()
            
            # Комбинировать дату и время
            event_start = trip_date.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )
            event_end = trip_date.replace(
                hour=end_time.hour,
                minute=end_time.minute,
                second=0,
                microsecond=0
            )
            
            # Форматировать для ICS (UTC)
            start_str = event_start.strftime("%Y%m%dT%H%M%S")
            end_str = event_end.strftime("%Y%m%dT%H%M%S")
            
            # Найти место для получения адреса
            place_address = ""
            for stop in trip_data.stops:
                if stop.google_place_id == time_slot.place_id:
                    place_address = stop.address or ""
                    break
            
            # Добавить событие
            ics_lines.extend([
                "BEGIN:VEVENT",
                f"UID:{trip_data.trip_id}-{time_slot.place_id}@travelpath.com",
                f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{start_str}",
                f"DTEND:{end_str}",
                f"SUMMARY:{time_slot.place_name}",
                f"DESCRIPTION:Visit {time_slot.place_name} ({time_slot.duration_minutes} minutes)",
                f"LOCATION:{place_address}",
                "STATUS:CONFIRMED",
                "SEQUENCE:0",
                "END:VEVENT",
            ])
        
        ics_lines.append("END:VCALENDAR")
        
        return "\r\n".join(ics_lines)
    
    def _export_gpx(self, trip_data: TripData) -> str:
        """
        Экспорт в GPX (GPS Exchange Format) для навигации
        
        Args:
            trip_data: Данные маршрута
            
        Returns:
            GPX строка (XML)
        """
        # Базовая структура GPX
        gpx_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gpx version="1.1" creator="TravelPath" xmlns="http://www.topografix.com/GPX/1/1">',
            f'  <metadata>',
            f'    <name>{trip_data.theme or "Trip"} - {trip_data.origin} to {trip_data.destination}</name>',
            f'    <desc>Trip created on {trip_data.created_at}</desc>',
            f'    <time>{datetime.utcnow().isoformat()}Z</time>',
            f'  </metadata>',
        ]
        
        # Добавить waypoints (точки интереса)
        for i, stop in enumerate(trip_data.stops):
            lat = stop.location.lat
            lon = stop.location.lng
            
            gpx_lines.extend([
                f'  <wpt lat="{lat}" lon="{lon}">',
                f'    <name>{stop.name}</name>',
                f'    <desc>{stop.address or ""}</desc>',
                f'    <type>waypoint</type>',
            ])
            
            # Добавить дополнительную информацию
            if stop.rating:
                gpx_lines.append(f'    <cmt>Rating: {stop.rating}/5</cmt>')
            
            gpx_lines.append(f'  </wpt>')
        
        # Добавить маршрут (route)
        gpx_lines.append('  <rte>')
        gpx_lines.append(f'    <name>{trip_data.theme or "Trip"} Route</name>')
        
        for stop in trip_data.stops:
            lat = stop.location.lat
            lon = stop.location.lng
            gpx_lines.extend([
                f'    <rtept lat="{lat}" lon="{lon}">',
                f'      <name>{stop.name}</name>',
                f'    </rtept>',
            ])
        
        gpx_lines.append('  </rte>')
        
        # Закрыть GPX
        gpx_lines.append('</gpx>')
        
        return '\n'.join(gpx_lines)
    
    def get_export_filename(
        self,
        trip_id: str,
        format: ExportFormat
    ) -> str:
        """
        Сгенерировать имя файла для экспорта
        
        Args:
            trip_id: ID маршрута
            format: Формат экспорта
            
        Returns:
            Имя файла
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = format.value
        return f"trip_{trip_id}_{timestamp}.{extension}"
    
    def get_mime_type(self, format: ExportFormat) -> str:
        """
        Получить MIME type для формата
        
        Args:
            format: Формат экспорта
            
        Returns:
            MIME type строка
        """
        mime_types = {
            ExportFormat.JSON: "application/json",
            ExportFormat.ICS: "text/calendar",
            ExportFormat.GPX: "application/gpx+xml",
            ExportFormat.PDF: "application/pdf",
        }
        return mime_types.get(format, "application/octet-stream")


# Global instance
export_service = ExportService()






