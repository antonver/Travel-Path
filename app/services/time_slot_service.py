"""
Service for calculating visit durations and time slots
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.models.schemas import Place, TimeSlot, TimeOfDay, EffortLevel
import logging

logger = logging.getLogger(__name__)


class TimeSlotService:
    """Service for managing time slots and visit durations"""
    
    # Базовая длительность посещения по типу места (в минутах)
    BASE_DURATIONS = {
        "museum": 120,
        "art_gallery": 90,
        "church": 45,
        "tourist_attraction": 60,
        "restaurant": 90,
        "cafe": 45,
        "bakery": 30,
        "bar": 60,
        "park": 90,
        "natural_feature": 120,
        "campground": 180,
        "amusement_park": 240,
        "bowling_alley": 120,
        "movie_theater": 150,
        "shopping_mall": 120,
        "zoo": 180,
        "aquarium": 120,
        "library": 60,
        "university": 45,
        "stadium": 120,
    }
    
    # Временные слоты
    TIME_SLOTS = {
        TimeOfDay.MORNING: {"start": "09:00", "end": "12:00"},
        TimeOfDay.AFTERNOON: {"start": "12:00", "end": "17:00"},
        TimeOfDay.EVENING: {"start": "17:00", "end": "21:00"},
    }
    
    # Рекомендуемое время дня для типов мест
    RECOMMENDED_TIME_OF_DAY = {
        "museum": TimeOfDay.MORNING,
        "art_gallery": TimeOfDay.MORNING,
        "church": TimeOfDay.MORNING,
        "park": TimeOfDay.MORNING,
        "natural_feature": TimeOfDay.MORNING,
        "restaurant": TimeOfDay.AFTERNOON,
        "cafe": TimeOfDay.AFTERNOON,
        "bar": TimeOfDay.EVENING,
        "amusement_park": TimeOfDay.AFTERNOON,
        "movie_theater": TimeOfDay.EVENING,
        "shopping_mall": TimeOfDay.AFTERNOON,
    }
    
    def estimate_visit_duration(
        self,
        place: Place,
        effort_level: EffortLevel = EffortLevel.MODERATE
    ) -> int:
        """
        Оценить длительность посещения места
        
        Args:
            place: Place объект
            effort_level: Уровень физической активности
            
        Returns:
            Длительность в минутах
        """
        # Базовая длительность по типу места
        base_duration = 60  # По умолчанию 1 час
        
        for place_type in place.types:
            if place_type in self.BASE_DURATIONS:
                base_duration = self.BASE_DURATIONS[place_type]
                break
        
        # Корректировка по уровню усилий
        effort_multipliers = {
            EffortLevel.VERY_EASY: 0.7,  # Пожилые люди - меньше времени
            EffortLevel.EASY: 0.85,
            EffortLevel.MODERATE: 1.0,
            EffortLevel.HARD: 1.2,  # Активные люди - больше времени
        }
        
        duration = int(base_duration * effort_multipliers[effort_level])
        
        # Минимум 15 минут, максимум 4 часа
        return max(15, min(duration, 240))
    
    def suggest_time_of_day(self, place: Place) -> TimeOfDay:
        """
        Предложить оптимальное время дня для посещения
        
        Args:
            place: Place объект
            
        Returns:
            TimeOfDay enum
        """
        # Проверяем типы места
        for place_type in place.types:
            if place_type in self.RECOMMENDED_TIME_OF_DAY:
                return self.RECOMMENDED_TIME_OF_DAY[place_type]
        
        # По умолчанию - день
        return TimeOfDay.AFTERNOON
    
    def generate_time_slots(
        self,
        places: List[Place],
        start_time: str = "09:00",
        effort_level: EffortLevel = EffortLevel.MODERATE,
        travel_times: Optional[List[int]] = None
    ) -> List[TimeSlot]:
        """
        Генерировать временные слоты для списка мест
        
        Args:
            places: Список мест для посещения
            start_time: Время начала (HH:MM)
            effort_level: Уровень физической активности
            travel_times: Время в пути между местами (в минутах)
            
        Returns:
            Список TimeSlot объектов
        """
        time_slots = []
        current_time = datetime.strptime(start_time, "%H:%M")
        
        for i, place in enumerate(places):
            # Оценить длительность посещения
            duration = self.estimate_visit_duration(place, effort_level)
            
            # Время окончания
            end_time = current_time + timedelta(minutes=duration)
            
            # Определить слот времени дня
            time_of_day = self._get_time_of_day_slot(current_time.time())
            
            # Создать TimeSlot
            time_slot = TimeSlot(
                place_id=place.google_place_id,
                place_name=place.name,
                time_of_day=time_of_day,
                start_time=current_time.strftime("%H:%M"),
                end_time=end_time.strftime("%H:%M"),
                duration_minutes=duration
            )
            
            time_slots.append(time_slot)
            
            # Обновить текущее время (добавить время посещения + время в пути)
            current_time = end_time
            
            # Добавить время в пути до следующего места
            if travel_times and i < len(travel_times):
                current_time += timedelta(minutes=travel_times[i])
            elif i < len(places) - 1:
                # По умолчанию 15 минут между местами
                current_time += timedelta(minutes=15)
        
        return time_slots
    
    def _get_time_of_day_slot(self, time: datetime.time) -> TimeOfDay:
        """
        Определить слот времени дня по времени
        
        Args:
            time: datetime.time объект
            
        Returns:
            TimeOfDay enum
        """
        hour = time.hour
        
        if 9 <= hour < 12:
            return TimeOfDay.MORNING
        elif 12 <= hour < 17:
            return TimeOfDay.AFTERNOON
        else:
            return TimeOfDay.EVENING
    
    def calculate_total_duration(
        self,
        places: List[Place],
        effort_level: EffortLevel = EffortLevel.MODERATE,
        travel_duration_minutes: int = 0
    ) -> int:
        """
        Рассчитать общую длительность поездки
        
        Args:
            places: Список мест
            effort_level: Уровень физической активности
            travel_duration_minutes: Общее время в пути
            
        Returns:
            Общая длительность в минутах
        """
        visit_duration = sum(
            self.estimate_visit_duration(place, effort_level)
            for place in places
        )
        
        return visit_duration + travel_duration_minutes
    
    def enrich_places_with_timing(
        self,
        places: List[Place],
        effort_level: EffortLevel = EffortLevel.MODERATE
    ) -> List[Place]:
        """
        Обогатить места информацией о времени посещения
        
        Args:
            places: Список мест
            effort_level: Уровень физической активности
            
        Returns:
            Обогащенный список мест
        """
        enriched_places = []
        
        for place in places:
            # Создать копию места
            place_dict = place.model_dump()
            
            # Добавить оценку длительности
            place_dict["estimated_visit_duration"] = self.estimate_visit_duration(
                place, effort_level
            )
            
            # Добавить рекомендуемое время дня
            place_dict["suggested_time_slot"] = self.suggest_time_of_day(place)
            
            # Создать новый Place объект
            enriched_place = Place(**place_dict)
            enriched_places.append(enriched_place)
        
        return enriched_places


# Global instance
time_slot_service = TimeSlotService()






