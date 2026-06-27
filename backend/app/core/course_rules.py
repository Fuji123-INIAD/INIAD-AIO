"""Static course rule registry for v0.3 task generation experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseRule:
    course_code: str
    deadline_rule: str
    submission_channel: str
    confidence: str
    notes: str
    description: str
    deadline_note: str
    submission_note: str
    caution_note: str


_COURSE_RULES: dict[str, CourseRule] = {
    "COT101": CourseRule(
        course_code="COT101",
        deadline_rule="next_lecture_previous_day",
        submission_channel="moocs",
        confidence="medium",
        notes=(
            "Assignment content is commonly in Slides, and submission is usually on MOOCs. "
            "Treat the deadline as the day before the next lecture."
        ),
        description="Slides や MOOCs の課題ページを確認し、次回授業までに必要な提出物がないか確認してください。",
        deadline_note="目安は次回授業の前日です。実際の締切は MOOCs の表示を優先してください。",
        submission_note="提出が必要な場合は、通常 MOOCs 上の提出場所を確認してください。",
        caution_note="Slides に課題説明が含まれることがあります。本文解析はまだ行っていません。",
    ),
    "SEM101": CourseRule(
        course_code="SEM101",
        deadline_rule="same_week_sunday_2359",
        submission_channel="email_to_instructor",
        confidence="medium",
        notes=(
            "Information is mostly in Slides. Submission is commonly sent by email "
            "to the instructor."
        ),
        description="授業資料や案内を確認し、必要な作業や提出指示がないか確認してください。",
        deadline_note="目安は同じ週の日曜日 23:59 です。授業内の明示指示を優先してください。",
        submission_note="提出が必要な場合は、教員へのメール提出指示を確認してください。",
        caution_note="メール宛先や件名などの細かい条件は、この一覧では確定していません。",
    ),
    "COT105": CourseRule(
        course_code="COT105",
        deadline_rule="explicit_or_unknown",
        submission_channel="moocs",
        confidence="low",
        notes="Prefer explicit HTML evidence because the format varies by instructor.",
        description="MOOCs の課題ページや授業資料を確認し、明示された課題がないか確認してください。",
        deadline_note="期限は明示情報がある場合のみ判断できます。この一覧では未確定です。",
        submission_note="提出が必要な場合は、MOOCs 上の案内や提出場所を確認してください。",
        caution_note="科目内の形式差が大きいため、必ず最新の MOOCs ページを確認してください。",
    ),
}


def normalize_course_code(course_code: str) -> str:
    return course_code.strip().upper()


def get_course_rule(course_code: str) -> CourseRule | None:
    return _COURSE_RULES.get(normalize_course_code(course_code))


def list_course_rules() -> dict[str, CourseRule]:
    return dict(_COURSE_RULES)
