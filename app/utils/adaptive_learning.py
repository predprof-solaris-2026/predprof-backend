from datetime import datetime
from typing import List, Dict, Optional, Tuple
from app.data.models import User, UserStats, UserAggregateStats, Task
from app.data.schemas import PersonalRecommendation, AdaptivePlan, UserPerformanceMetrics


MASTERY_THRESHOLDS = {
    "лёгкий": {"accuracy": 0.90, "speed": 30000},
    "средний": {"accuracy": 0.75, "speed": 60000},
    "сложный": {"accuracy": 0.60, "speed": 120000},
}

TARGET_METRICS = {
    "лёгкий": {"accuracy": 0.95, "speed": 20000},
    "средний": {"accuracy": 0.85, "speed": 45000},
    "сложный": {"accuracy": 0.75, "speed": 90000}, 
}

THEME_TO_KEY = {
    "математика": "Theme.math",
    "русский": "Theme.russian",
    "информатика": "Theme.informatic",
    "физика": "Theme.physics",
}


async def calculate_user_metrics(user_id: str) -> UserPerformanceMetrics:    
    user_stats = await UserStats.find_one({"user_id": user_id})
    
    if not user_stats or user_stats.attempts == 0:
        return UserPerformanceMetrics(
            total_attempts=0,
            accuracy_rate=0.0,
            avg_response_time_ms=0.0,
            topics_mastered=[],
            topics_struggling=[],
            topics_not_attempted=[]
        )
    
    total_attempts = user_stats.attempts
    accuracy_rate = user_stats.correct / total_attempts if total_attempts > 0 else 0.0
    avg_response_time = user_stats.avg_time_ms or 0.0
    
    topics_mastered = []
    topics_struggling = []
    topics_not_attempted = []
    topics_in_progress = []
    
    all_themes = ["математика", "русский", "информатика", "физика"]
    
    for theme in all_themes:
        theme_key = THEME_TO_KEY.get(theme)
        theme_stat = user_stats.by_theme.get(theme_key) if theme_key else None
        
        if not theme_stat or theme_stat.attempts == 0:
            topics_not_attempted.append(theme)
        else:
            theme_accuracy = theme_stat.correct / theme_stat.attempts
            
            if theme_accuracy >= 0.80:
                topics_mastered.append(theme)
            elif theme_accuracy < 0.50:
                topics_struggling.append(theme)
            else:
                topics_in_progress.append(theme)
    
    return UserPerformanceMetrics(
        total_attempts=total_attempts,
        accuracy_rate=accuracy_rate,
        avg_response_time_ms=avg_response_time,
        topics_mastered=topics_mastered,
        topics_struggling=topics_struggling,
        topics_not_attempted=topics_not_attempted,
        topics_in_progress=topics_in_progress
    )


async def theme_difficulty(user_id: str, theme: str) -> Dict[str, float]:
    user_stats = await UserStats.find_one({"user_id": user_id})
    
    if not user_stats:
        return {"easy": 0.0, "medium": 0.0, "hard": 0.0}
    
    theme_key = THEME_TO_KEY.get(theme)
    theme_stat = user_stats.by_theme.get(theme_key) if theme_key else None
    
    if not theme_stat or theme_stat.attempts == 0:
        return {"easy": 0.0, "medium": 0.0, "hard": 0.0}
    
    overall_accuracy = theme_stat.correct / theme_stat.attempts
    easy_accuracy = min(overall_accuracy + 0.15, 1.0)
    medium_accuracy = overall_accuracy
    hard_accuracy = max(overall_accuracy - 0.20, 0.0)
    
    return {
        "easy": easy_accuracy,
        "medium": medium_accuracy,
        "hard": hard_accuracy,
    }


def generate_recommendation(
    theme: str,
    current_accuracy: float,
    is_struggling: bool,
    not_attempted: bool,
) -> Optional[PersonalRecommendation]:    
    if not_attempted:
        return PersonalRecommendation(
            theme=theme,
            difficulty="лёгкий",
            reason=f"Вы ещё не пробовали задачи по теме '{theme}'. Начните с простых!",
            priority=3
        )
    
    if is_struggling:
        return PersonalRecommendation(
            theme=theme,
            difficulty="лёгкий",
            reason=f"Низкая точность по теме '{theme}' (менее 50%). Повторите основы на лёгких задачах.",
            priority=5
        )
    
    easy_threshold = MASTERY_THRESHOLDS["лёгкий"]["accuracy"]
    if current_accuracy >= easy_threshold:
        return PersonalRecommendation(
            theme=theme,
            difficulty="средний",
            reason=f"Вы хорошо решаете лёгкие задачи по '{theme}' ({int(current_accuracy*100)}% точность). Пора повышать сложность!",
            priority=4
        )
    
    if current_accuracy >= 0.65:
        return PersonalRecommendation(
            theme=theme,
            difficulty="лёгкий",
            reason=f"Продолжите решать лёгкие задачи по '{theme}' ({int(current_accuracy*100)}% точность) для лучшего закрепления.",
            priority=2
        )
    
    return None


async def individual_plan(user_id: str) -> AdaptivePlan:
    metrics = await calculate_user_metrics(user_id)
    recommendations = []
    # print(user_id)
    user_stats = await UserStats.find_one(UserStats.user_id == user_id)
    
    if metrics.total_attempts == 0:
        all_themes = ["математика", "русский", "информатика", "физика"]
        for idx, theme in enumerate(all_themes):
            rec = PersonalRecommendation(
                theme=theme,
                difficulty="лёгкий",
                reason=f"Начните с простых задач по теме {theme}",
                priority=4 - idx
            )
            recommendations.append(rec)
    else:
        for theme in metrics.topics_not_attempted:
            theme_key = THEME_TO_KEY.get(theme)
            theme_stat = user_stats.by_theme.get(theme_key) if user_stats and theme_key else None
            is_truly_not_attempted = not theme_stat or theme_stat.attempts == 0
            
            if theme_stat and theme_stat.attempts > 0:
                current_accuracy = theme_stat.correct / theme_stat.attempts
                is_struggling = current_accuracy < 0.50
            else:
                current_accuracy = 0.0
                is_struggling = False
            
            rec = generate_recommendation(
                theme=theme,
                current_accuracy=current_accuracy,
                is_struggling=is_struggling,
                not_attempted=is_truly_not_attempted
            )
            if rec:
                recommendations.append(rec)
        
        for theme in metrics.topics_struggling:
            theme_stats = await theme_difficulty(user_id, theme)
            rec = generate_recommendation(
                theme=theme,
                current_accuracy=theme_stats["easy"],
                is_struggling=True,
                not_attempted=False
            )
            if rec:
                recommendations.append(rec)
        
        for theme in metrics.topics_in_progress:
            theme_stats = await theme_difficulty(user_id, theme)
            rec = generate_recommendation(
                theme=theme,
                current_accuracy=theme_stats["medium"],
                is_struggling=False,
                not_attempted=False
            )
            if rec:
                recommendations.append(rec)
        
        for theme in metrics.topics_mastered:
            theme_stats = await theme_difficulty(user_id, theme)
            
            medium_threshold = MASTERY_THRESHOLDS["средний"]["accuracy"]
            hard_threshold = MASTERY_THRESHOLDS["сложный"]["accuracy"]
            
            if theme_stats["hard"] >= hard_threshold:
                rec = PersonalRecommendation(
                    theme=theme,
                    difficulty="сложный",
                    reason=f"Отличная работа! Вы готовы к сложным задачам по теме {theme}.",
                    priority=3
                )
            elif theme_stats["medium"] >= medium_threshold:
                rec = PersonalRecommendation(
                    theme=theme,
                    difficulty="средний",
                    reason=f"Хороший прогресс по теме {theme}. Переходите на более сложные задачи!",
                    priority=2
                )
            else:
                rec = PersonalRecommendation(
                    theme=theme,
                    difficulty="лёгкий",
                    reason=f"Продолжайте закреплять знания по теме {theme} на лёгких задачах.",
                    priority=1
                )
            
            recommendations.append(rec)
    
    recommendations.sort(key=lambda r: r.priority, reverse=True)
    
    overall_accuracy = metrics.accuracy_rate
    target_accuracy = min(overall_accuracy + 0.10, 0.95)
    target_speed = max(metrics.avg_response_time_ms - 5000, 15000)
    
    estimated_days = max(1, len(recommendations)) 
    
    return AdaptivePlan(
        user_id=user_id,
        recommendations=recommendations,
        target_accuracy=target_accuracy,
        target_speed_ms=int(target_speed),
        estimated_completion_days=estimated_days
    )


async def recommended_task(user_id: str, current_theme: Optional[str] = None) -> Optional[Dict]:    
    user_plan = await individual_plan(user_id)
    
    if not user_plan.recommendations:
        all_tasks = await Task.find({"is_published": True}).limit(1).to_list()
        return {"id": str(all_tasks[0].id), "reason": "У вас нет специальных рекомендаций, поэтому мы выбрали случайную задачу"} if all_tasks else None
    
    top_rec = user_plan.recommendations[0]
    task = await Task.find_one({
        "is_published": True,
        "theme": top_rec.theme,
        "difficulty": top_rec.difficulty
    })
    
    if task:
        return {
            "id": str(task.id),
            "theme": top_rec.theme,
            "difficulty": top_rec.difficulty,
            "reason": top_rec.reason
        }
    
    return None


async def update_adaptive_metrics(user_id: str, task_id: str, is_correct: bool, elapsed_ms: int) -> None:
    task = await Task.get(task_id)
    if not task:
        return
    
    user_stats = await UserStats.find_one({"user_id": user_id})
    if not user_stats:
        return
    pass
