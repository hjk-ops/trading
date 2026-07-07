"""🎯 수능 학습 진단 시스템 (V1: 수학).

핵심 로직 — 한계 점수 효율:
  우선순위 = 잃은 점수(틀린 배점 합) × 회복 난이도 보정
  "정답률 80% 단원을 다듬는 것보다 20% 단원을 끌어올리는 게 점수 상승폭이 크다"

문항→단원 매핑은 수능 수학의 일반적 출제 구성 기반 템플릿(시험별로 다를 수 있음,
문항별 단원은 입력 화면에서 수정 가능).
"""

# 수능 수학 일반 구성 템플릿: (문항번호, 기본배점, 기본단원)
# 공통 1~22 (수학I/수학II), 선택 23~30
MATH_TEMPLATE = {
    "common": [
        (1, 2, "지수로그"), (2, 2, "미분법(수2)"), (3, 3, "수열"), (4, 3, "함수의극한"),
        (5, 3, "삼각함수"), (6, 3, "미분법(수2)"), (7, 3, "지수로그"), (8, 3, "적분법(수2)"),
        (9, 4, "삼각함수"), (10, 4, "적분법(수2)"), (11, 4, "수열"), (12, 4, "미분법(수2)"),
        (13, 4, "지수로그"), (14, 4, "미분법(수2)"), (15, 4, "수열"),
        (16, 3, "지수로그"), (17, 3, "미분법(수2)"), (18, 3, "수열"), (19, 3, "삼각함수"),
        (20, 4, "적분법(수2)"), (21, 4, "지수로그"), (22, 4, "미분법(수2)"),
    ],
    "select": {
        "미적분": [(23, 2, "수열의극한"), (24, 3, "미분법(미적)"), (25, 3, "적분법(미적)"),
                 (26, 3, "수열의극한"), (27, 3, "미분법(미적)"), (28, 4, "미분법(미적)"),
                 (29, 4, "적분법(미적)"), (30, 4, "미분법(미적)")],
        "확률과통계": [(23, 2, "경우의수"), (24, 3, "확률"), (25, 3, "확률"),
                   (26, 3, "통계"), (27, 3, "경우의수"), (28, 4, "확률"),
                   (29, 4, "통계"), (30, 4, "통계")],
        "기하": [(23, 2, "이차곡선"), (24, 3, "평면벡터"), (25, 3, "이차곡선"),
               (26, 3, "공간도형"), (27, 3, "평면벡터"), (28, 4, "이차곡선"),
               (29, 4, "공간도형"), (30, 4, "공간도형")],
    },
    "units": ["지수로그", "삼각함수", "수열", "함수의극한", "미분법(수2)", "적분법(수2)",
              "수열의극한", "미분법(미적)", "적분법(미적)",
              "경우의수", "확률", "통계", "이차곡선", "평면벡터", "공간도형"],
}

KOREAN_TEMPLATE = {
    # 공통 34문항 = 76점 (2점 26개 + 3점 8개), 선택 11문항 = 24점 (2점 9개 + 3점 5개... )
    "common": (
        [(i, 3 if i in (6, 10, 14, 17) else 2, "독서") for i in range(1, 18)] +
        [(i, 3 if i in (22, 27, 30, 33) else 2, "문학") for i in range(18, 35)]
    ),
    "select": {
        "화법과작문": [(i, 3 if i in (40, 43) else 2, "화법과작문")
                    for i in range(35, 46)],
        "언어와매체": [(i, 3 if i in (40, 43) else 2, "언어와매체")
                    for i in range(35, 46)],
    },
}

ENGLISH_TEMPLATE = {
    "common": (
        [(i, 2, "듣기") for i in range(1, 18)] +
        [(18, 2, "글의목적"), (19, 2, "심경분위기"), (20, 2, "주장"),
         (21, 3, "함축의미"), (22, 3, "요지"), (23, 2, "주제"), (24, 2, "제목"),
         (25, 2, "도표"), (26, 2, "내용일치"), (27, 2, "실용문"), (28, 2, "실용문"),
         (29, 3, "어법"), (30, 3, "어휘"),
         (31, 2, "빈칸추론"), (32, 3, "빈칸추론"), (33, 3, "빈칸추론"), (34, 3, "빈칸추론"),
         (35, 2, "무관한문장"), (36, 2, "순서배열"), (37, 3, "순서배열"),
         (38, 2, "문장삽입"), (39, 3, "문장삽입"), (40, 3, "요약문"),
         (41, 2, "장문독해"), (42, 2, "장문독해"), (43, 2, "장문독해"),
         (44, 2, "장문독해"), (45, 2, "장문독해")]
    ),
    "select": {},
}

# 과목별 등급컷 (근사치 — 시험 난이도에 따라 변동, 영어는 절대평가 고정)
SUBJECTS = {
    "수학": {"template": MATH_TEMPLATE, "cut": {1: 84, 2: 76, 3: 65, 4: 52, 5: 40}},
    "국어": {"template": KOREAN_TEMPLATE, "cut": {1: 85, 2: 78, 3: 68, 4: 56, 5: 44}},
    "영어": {"template": ENGLISH_TEMPLATE, "cut": {1: 90, 2: 80, 3: 70, 4: 60, 5: 50}},
}
GRADE_CUT = SUBJECTS["수학"]["cut"]


def diagnose(questions, target_grade, subject="수학"):
    """questions: [{no, pts, unit, correct}] → 진단 결과 dict."""
    cut = SUBJECTS.get(subject, SUBJECTS["수학"])["cut"]
    score = sum(q["pts"] for q in questions if q["correct"])
    total = sum(q["pts"] for q in questions)
    target = cut.get(int(target_grade), 84)
    gap = max(0, target - score)

    units = {}
    for q in questions:
        u = units.setdefault(q["unit"], {"unit": q["unit"], "total": 0, "got": 0,
                                         "lost_pts": 0, "n": 0, "n_ok": 0})
        u["total"] += q["pts"]; u["n"] += 1
        if q["correct"]:
            u["got"] += q["pts"]; u["n_ok"] += 1
        else:
            u["lost_pts"] += q["pts"]

    ranked = []
    for u in units.values():
        acc = u["n_ok"] / u["n"]
        # 회복 기대치: 잃은 점수의 60%를 회복 가능하다고 가정 (전멸 단원은 기초부터라 50%)
        recover = u["lost_pts"] * (0.5 if acc == 0 else 0.6)
        # 우선순위: 회복 기대 점수 (잃은 게 많고 배점이 큰 단원이 위로)
        ranked.append({**u, "acc": round(acc * 100),
                       "expected_gain": round(recover, 1)})
    ranked.sort(key=lambda x: (-x["expected_gain"], x["acc"]))

    # 학습 플랜: 갭을 메울 때까지 상위 단원부터
    plan, cum = [], 0
    for u in ranked:
        if u["lost_pts"] == 0:
            continue
        cum += u["expected_gain"]
        plan.append({"unit": u["unit"], "acc": u["acc"], "lost": u["lost_pts"],
                     "gain": u["expected_gain"], "cum": round(cum, 1),
                     "enough": cum >= gap})
        if cum >= gap and len(plan) >= 2:
            break

    return {"score": score, "total": total, "target": target, "gap": gap,
            "grade_now": next((g for g, c in sorted(cut.items())
                               if score >= c), 5),
            "units": ranked, "plan": plan}
