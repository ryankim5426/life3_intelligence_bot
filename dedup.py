# -*- coding: utf-8 -*-
"""제목이 달라도 같은 기사면 한 번만 보내기 위한 유사도 판정.

한 사건을 여러 언론사가 조금씩 다른 제목으로 내보내기 때문에,
제목이 정확히 같을 때만 걸러내면 중복이 그대로 쌓입니다.
여기서는 두 가지를 봅니다.

  1) 글자 2글자 묶음(bigram)의 겹치는 비율
  2) 따옴표 안의 고유명사 일치 ('노블리에 콘서트' 등)

짧은 제목일수록 단어 하나 차이가 크게 작용하므로 기준을 더 엄격하게 둡니다.
(예: "3분기 실적 발표"와 "2분기 실적 발표"는 합쳐지면 안 됨)
"""

import re

_BRACKET = re.compile(r"[\[\(<【][^\]\)>】]{0,20}[\]\)>】]")
_QUOTED = re.compile(r"['\"‘’“”「」『』]([^'\"‘’“”「」『』]{2,20})['\"‘’“”「」『』]")
_PUNCT = re.compile(r"[^0-9A-Za-z가-힣]+")

# 제목 앞뒤에 습관적으로 붙는 말머리 — 비교에서 제외
_STOPWORDS = ("단독", "속보", "종합", "포토", "영상", "인터뷰", "오늘의", "기획")


def normalize(title):
    """말머리·기호·공백을 걷어낸 비교용 문자열."""
    text = _BRACKET.sub(" ", title or "")
    text = _PUNCT.sub("", text)
    for word in _STOPWORDS:
        text = text.replace(word, "")
    return text


def _bigrams(text):
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def similarity(norm_a, norm_b):
    """0.0 ~ 1.0. 두 정규화 제목이 얼마나 겹치는지."""
    ga, gb = _bigrams(norm_a), _bigrams(norm_b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _threshold(norm_a, norm_b):
    shorter = min(len(norm_a), len(norm_b))
    if shorter < 15:
        return 0.70      # 짧은 제목: 단어 하나만 달라도 다른 기사일 수 있음
    if shorter < 21:
        return 0.50
    return 0.38          # 긴 제목: 표현이 달라도 같은 사건일 가능성이 큼


def quoted_terms(title):
    """따옴표로 묶인 고유명사 — 상품명·행사명 등."""
    out = set()
    for hit in _QUOTED.findall(title or ""):
        term = _PUNCT.sub("", hit)
        if len(term) >= 3:
            out.add(term)
    return out


def is_same_story(title_a, title_b):
    """두 제목이 같은 기사인지."""
    na, nb = normalize(title_a), normalize(title_b)
    if not na or not nb:
        return False
    score = similarity(na, nb)
    if score >= _threshold(na, nb):
        return True
    # 제목 표현이 크게 달라도 같은 고유명사를 인용했다면 같은 건으로 봄
    if quoted_terms(title_a) & quoted_terms(title_b) and score >= 0.20:
        return True
    return False
