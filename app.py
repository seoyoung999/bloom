import sqlite3
import random
import json
from flask import Flask, request, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np
from datetime import datetime
import traceback

# --- 초기 설정 ---
app = Flask(__name__)
DATABASE = 'database.db'

# --- 데이터베이스 연결 함수 ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# --- 텍스트 감성 분석 모델 로드 ---
print("kcbert-base 모델을 로드하고 있습니다...")
try:
    MODEL_NAME = "beomi/kcbert-base"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    print("모델 로드 완료.")
except Exception as e:
    print(f"모델 로드 중 오류 발생: {e}")
    # exit() # 필요하다면 활성화

# --- 분석 로직 설정 ---
labels = ['Negative', 'Neutral', 'Positive']
emotion_map = {'Negative': 0, 'Neutral': 1, 'Positive': 2}

# 키워드 목록 (오류 방지용 안전장치)
POSITIVE_KEYWORDS = [
    "행복", "기쁨", "즐거", "신나", "최고", "좋았", "훌륭", "알찬", "만족", "좋다", "괜찮", 
    "뿌듯", "감사", "평온", "설렘", "기대", "상쾌", "편안", "활기", "재미있"
]
NEGATIVE_KEYWORDS = [
    "슬픔", "우울", "화나", "짜증", "최악", "힘들", "괴로", "지침", "피곤", "안좋", "별로", 
    "안 좋다", "속상", "실망", "불안", "걱정", "무기력", "답답", "귀찮", "외롭", "후회"
]

# 텍스트 감정 분석 함수
def analyze_text_emotion(text):
    try:
        if not text or not isinstance(text, str):
            return 'Neutral', 0.5
        
        text_lower = text.lower()
        
        # 1. 긍정 키워드 우선 확인
        for keyword in POSITIVE_KEYWORDS:
            if keyword == text_lower:
                return 'Positive', 1.0
            
            # 짧은 키워드 (2글자 이하)
            if len(keyword) <= 2:
                 if f" {keyword} " in f" {text_lower} " or text_lower.startswith(keyword + " ") or text_lower.endswith(" " + keyword):
                      is_negated = False
                      # "좋다"의 경우 부정형 체크 ("안 좋다" 등)
                      if keyword == "좋다":
                          if "안 좋다" in text_lower or "않 좋다" in text_lower or "별로 좋다" in text_lower:
                              is_negated = True
                      if not is_negated:
                          return 'Positive', 1.0
            # 긴 키워드
            elif keyword in text_lower:
                 is_negated = False
                 if keyword == "좋았":
                     if "안 좋았" in text_lower or "않 좋았" in text_lower:
                         is_negated = True
                 if not is_negated:
                     return 'Positive', 1.0
        
        # 2. 부정 키워드 우선 확인
        for keyword in NEGATIVE_KEYWORDS:
             if keyword == text_lower:
                 return 'Negative', 1.0
             if keyword != "안 좋다" and (f" {keyword} " in f" {text_lower} " or text_lower.startswith(keyword + " ") or text_lower.endswith(" " + keyword)):
                 return 'Negative', 1.0
             if keyword == "안 좋다" and keyword in text_lower:
                 return 'Negative', 1.0

        # 3. 키워드가 없으면 AI 모델로 분석
        inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
        with torch.no_grad():
            outputs = model(**inputs)
        
        probs = torch.nn.functional.softmax(outputs.logits, dim=1)
        scores = probs.detach().cpu().numpy()[0]
        max_idx = np.argmax(scores)
        
        return labels[max_idx], scores[max_idx]
        
    except Exception as e:
        print(f"텍스트 감성 분석 중 오류 발생: {e}")
        return 'Neutral', 0.5

# 종합 점수 계산 함수 (요청하신 비율 적용: 기분 35%, 수면 15%, 활동 20%, 텍스트 30%)
def calculate_total_score(mood, sleep, activity, feeling_text):
    try:
        # KCBERT 및 키워드로 텍스트 감정 분석
        text_emotion, _ = analyze_text_emotion(feeling_text)
        
        mood = int(mood) if mood is not None else 5
        sleep = int(sleep) if sleep is not None else 6
        activity = int(activity) if activity is not None else 5

        # 텍스트 점수 변환 (Negative: 0점, Neutral: 5점, Positive: 10점)
        text_score = emotion_map.get(text_emotion, 1) * 5
        
        # 수면 시간 보정 (최소 4시간으로 계산)
        sleep_adj = max(sleep, 4)

        # --- 점수 계산 로직 ---
        # 기분(35%) + 수면(15%) + 활동(20%) + 텍스트(30%)
        mood_w = mood * 0.35
        sleep_w = sleep_adj * 0.15
        activity_w = activity * 0.2
        text_w = text_score * 0.3
        
        combined_score = mood_w + sleep_w + activity_w + text_w
        
        # 부정 감정 상한선 적용 (텍스트가 부정적인데 점수가 너무 높으면 보정)
        cap_applied = False
        if text_emotion == 'Negative' and combined_score > 6.0:
            combined_score = 6.0
            cap_applied = True

        # 최종 점수는 0~10 사이로 제한
        combined_score = max(0, min(10, combined_score))

        # 계산 내역 생성 (프론트엔드 표시용)
        breakdown = {
            'mood_calc': f"{mood}점 × 35% = {mood_w:.2f}",
            'sleep_calc': f"{sleep_adj}시간(보정) × 15% = {sleep_w:.2f}",
            'activity_calc': f"{activity}점 × 20% = {activity_w:.2f}",
            'text_calc': f"{text_emotion}({text_score}점) × 30% = {text_w:.2f}",
            'total_raw': f"{mood_w + sleep_w + activity_w + text_w:.2f}",
            'cap_applied': cap_applied
        }

        return combined_score, text_emotion, breakdown
    except Exception as e:
        print(f"점수 계산 중 오류 발생: {e}")
        return 5.0, 'Neutral', {}

# 점수에 따른 감정 상태 텍스트 분류
def classify_emotion_by_combined_score(score):
    if score <= 3: return "매우 나쁨"
    elif score <= 5: return "나쁨"
    elif score <= 7: return "보통"
    elif score <= 8.5: return "긍정적"
    else: return "매우 긍정적"

# --- 챌린지 데이터 풀 (링크 안전성 확보 및 대폭 확장) ---
CHALLENGES_POOL = {
    'video': [
        # Low Energy (차분함, 힐링)
        {'title': '5분 명상: 불안과 스트레스 해소', 'url': 'https://www.youtube.com/results?search_query=5분+명상+불안+해소', 'energy': 'low'},
        {'title': '지브리 스튜디오 피아노 음악', 'url': 'https://www.youtube.com/results?search_query=지브리+피아노+모음', 'energy': 'low'},
        {'title': '마음이 편안해지는 자연 소리 (ASMR)', 'url': 'https://www.youtube.com/results?search_query=자연+소리+ASMR', 'energy': 'low'},
        {'title': '심신 안정을 위한 힐링 주파수', 'url': 'https://www.youtube.com/results?search_query=힐링+주파수', 'energy': 'low'},
        # Medium Energy (기분 전환, 흥미)
        {'title': '기분 전환을 위한 웃긴 동물 영상', 'url': 'https://www.youtube.com/results?search_query=웃긴+동물+영상+모음', 'energy': 'medium'},
        {'title': '활력을 주는 아침 스트레칭 가이드', 'url': 'https://www.youtube.com/results?search_query=아침+활력+스트레칭', 'energy': 'medium'},
        {'title': '방구석 콘서트: 신나는 팝송 모음', 'url': 'https://www.youtube.com/results?search_query=신나는+팝송+모음', 'energy': 'medium'},
        {'title': '짧고 굵은 동기부여 영상', 'url': 'https://www.youtube.com/results?search_query=짧은+동기부여+영상', 'energy': 'medium'},
        # High Energy (에너지 발산, 성장)
        {'title': 'TED 강연: 변화와 성장의 이야기', 'url': 'https://www.youtube.com/results?search_query=TED+강연+변화+성장', 'energy': 'high'},
        {'title': '집에서 즐기는 줌바 댄스', 'url': 'https://www.youtube.com/results?search_query=집에서+줌바댄스', 'energy': 'high'},
        {'title': '고강도 홈트레이닝 (타바타)', 'url': 'https://www.youtube.com/results?search_query=타바타+운동', 'energy': 'high'},
        {'title': '세상을 바꾸는 시간 15분 (세바시)', 'url': 'https://www.youtube.com/results?search_query=세바시+레전드', 'energy': 'high'},
    ],
    'activity': [
        # Low Energy (정적 활동)
        {'title': '창문 열고 5번 깊게 숨쉬기', 'url': '#', 'energy': 'low'},
        {'title': '따뜻한 차나 물 한 잔 마시기', 'url': '#', 'energy': 'low'},
        {'title': '눈 감고 3분간 아무 생각 안 하기', 'url': '#', 'energy': 'low'},
        {'title': '반려식물 물 주기 및 잎 닦아주기', 'url': '#', 'energy': 'low'},
        {'title': '좋아하는 향수나 캔들 향 맡기', 'url': '#', 'energy': 'low'},
        # Medium Energy (가벼운 활동)
        {'title': '가벼운 15분 동네 산책하기', 'url': '#', 'energy': 'medium'},
        {'title': '좋아하는 노래 크게 틀고 따라부르기', 'url': '#', 'energy': 'medium'},
        {'title': '책상 위나 지갑 정리하기', 'url': '#', 'energy': 'medium'},
        {'title': '스마트폰 사진첩 정리하며 추억 여행', 'url': '#', 'energy': 'medium'},
        {'title': '간단한 셀프 마사지 (목, 어깨)', 'url': 'https://www.youtube.com/results?search_query=셀프+목+어깨+마사지', 'energy': 'medium'},
        # High Energy (동적 활동)
        {'title': '오랜만에 친구에게 전화 걸어 수다 떨기', 'url': '#', 'energy': 'high'},
        {'title': '방 전체 청소기 돌리고 환기하기', 'url': '#', 'energy': 'high'},
        {'title': '플랭크 1분 도전하기', 'url': 'https://www.youtube.com/results?search_query=올바른+플랭크+자세', 'energy': 'high'},
        {'title': '가까운 공원이나 뒷산 다녀오기', 'url': '#', 'energy': 'high'},
        {'title': '새로운 요리 레시피 도전해보기', 'url': 'https://www.10000recipe.com/', 'energy': 'high'},
    ],
    'creative': [
        # Low Energy (사색, 기록)
        {'title': '지금 드는 감정 3단어로 표현해보기', 'url': '#', 'energy': 'low'},
        {'title': '좋아하는 시 한 편 필사하기', 'url': 'https://search.naver.com/search.naver?query=좋은+시+추천', 'energy': 'low'},
        {'title': '내일의 할 일 목록(To-Do List) 작성하기', 'url': '#', 'energy': 'low'},
        {'title': '감사일기: 오늘 고마웠던 것 3가지 쓰기', 'url': '#', 'energy': 'low'},
        # Medium Energy (표현, 꾸미기)
        {'title': '컬러링북이나 만다라 색칠하기', 'url': 'https://search.naver.com/search.naver?query=무료+만다라+도안', 'energy': 'medium'},
        {'title': '스마트폰으로 하늘이나 풍경 사진 찍기', 'url': '#', 'energy': 'medium'},
        {'title': '나만의 플레이리스트 만들기', 'url': '#', 'energy': 'medium'},
        {'title': '블로그에 오늘의 일기 남기기', 'url': 'https://section.blog.naver.com/', 'energy': 'medium'},
        # High Energy (창작, 기획)
        {'title': '그림 그리기 (드로잉, 수채화 등)', 'url': 'https://www.youtube.com/results?search_query=초보+드로잉+강좌', 'energy': 'high'},
        {'title': 'DIY 키트나 종이접기 해보기', 'url': 'https://www.youtube.com/results?search_query=종이접기', 'energy': 'high'},
        {'title': '나중에 가고 싶은 여행 계획 짜보기', 'url': 'https://www.google.com/maps', 'energy': 'high'},
        {'title': '짧은 소설이나 에세이 써보기', 'url': '#', 'energy': 'high'},
    ]
}

# 피드백 점수 조회 함수
def get_challenge_feedback_scores():
    conn = get_db_connection()
    try:
        feedback_data = conn.execute(
            "SELECT challenge_title, SUM(CASE rating WHEN 1 THEN 1 WHEN -1 THEN -1 ELSE 0 END) as score FROM challenge_feedback GROUP BY challenge_title"
        ).fetchall()
        scores = {row['challenge_title']: row['score'] for row in feedback_data}
    except sqlite3.OperationalError:
        scores = {}
    finally:
        conn.close()
    return scores

# 동적 챌린지 추천 함수
def get_dynamic_challenges(mood, sleep, activity, feeling_text):
    try:
        feedback_scores = get_challenge_feedback_scores()
        
        # 에너지 레벨 계산
        avg_score = (int(mood) + int(activity)) / 2
        sleep_val = int(sleep)
        
        if sleep_val < 5 or avg_score < 4:
            energy_level = 'low'
        elif avg_score < 7:
            energy_level = 'medium'
        else:
            energy_level = 'high'
        
        # 적합한 챌린지 필터링
        suitable_challenges = []
        for category in CHALLENGES_POOL.values():
            suitable_challenges.extend([c for c in category if c.get('energy') == energy_level])
        
        # 텍스트 내용 기반 추가 추천
        feeling_text_safe = feeling_text if feeling_text else ""
        if "불안" in feeling_text_safe or "걱정" in feeling_text_safe:
            suitable_challenges.append({'title': '불안감을 다스리는 호흡법 따라하기', 'url': 'https://www.youtube.com/results?search_query=불안+해소+호흡법', 'energy': 'low'})
        elif "지루" in feeling_text_safe or "심심" in feeling_text_safe:
            suitable_challenges.append({'title': '흥미로운 단편 소설 읽기', 'url': 'https://brunch.co.kr/keyword/%EB%8B%A8%ED%8E%B8%EC%86%8C%EC%84%A4', 'energy': 'medium'})
        
        # 중복 제거
        unique_challenges = list({frozenset(item.items()): item for item in suitable_challenges}.values())

        if not unique_challenges:
             return [{'title': '가벼운 스트레칭 하기', 'url': '#', 'type': '활동'}] * 3

        # 가중치 계산 (피드백 반영)
        weights = [max(0.1, 1 + feedback_scores.get(c['title'], 0)) for c in unique_challenges]
        
        if not weights or sum(weights) <= 0:
             selected_challenges = random.sample(unique_challenges, min(3, len(unique_challenges)))
        else:
            selected_challenges = []
            temp_suitable = list(unique_challenges)
            temp_weights = list(weights)

            # 가중치 기반 랜덤 선택 (최대 3개)
            while len(selected_challenges) < 3 and len(temp_suitable) > 0:
                if sum(temp_weights) <= 0: break
                try:
                    chosen_list = random.choices(temp_suitable, weights=temp_weights, k=1)
                    if chosen_list:
                        chosen = chosen_list[0]
                        if chosen not in selected_challenges:
                             selected_challenges.append(chosen)
                        idx = temp_suitable.index(chosen)
                        temp_suitable.pop(idx)
                        temp_weights.pop(idx)
                        if not temp_weights: break
                    else: break
                except ValueError:
                    break
        
        # 부족한 개수 채우기
        remaining_candidates = [c for c in unique_challenges if c not in selected_challenges]
        needed = 3 - len(selected_challenges)
        if needed > 0 and remaining_candidates:
            selected_challenges.extend(random.sample(remaining_candidates, min(needed, len(remaining_candidates))))

        # 챌린지 타입 결정 및 최종 리스트 생성
        final_selection = []
        for c in selected_challenges[:3]:
            url = c.get('url', '#')
            new_c = c.copy()
            if 'youtube.com' in url or 'youtu.be' in url:
                new_c['type'] = '유튜브'
            elif 'search.naver.com' in url or 'brunch.co.kr' in url or 'pinterest.co.kr' in url or 'goodnewsnetwork.org' in url or '10000recipe.com' in url or 'google.com/maps' in url:
                new_c['type'] = '웹사이트/블로그'
            elif url == '#':
                new_c['type'] = '활동'
            else:
                new_c['type'] = '기타'
            final_selection.append(new_c)
        
        # 그래도 3개가 안되면 기본 챌린지로 채움
        while len(final_selection) < 3:
             final_selection.append({'title': '잠시 눈 감고 휴식하기', 'url': '#', 'type': '활동'})

        return final_selection
    except Exception:
        return [{'title': '가벼운 스트레칭 하기', 'url': '#', 'type': '활동'}] * 3

# --- 챗봇 질문 ---
options_template = [{"text": "전혀 없음 (0점)", "score": 0}, {"text": "며칠 동안 (1점)", "score": 1}, {"text": "일주일 이상 (2점)", "score": 2}, {"text": "거의 매일 (3점)", "score": 3}]
PHQ9_QUESTIONS = [{"id": i+1, "text": q, "options": options_template} for i, q in enumerate(["1. 😞 거의 매일 우울하거나 기분이 처졌던 날이 있었나요?", "2. 😐 거의 매일 흥미나 즐거움이 줄어든 적이 있었나요?", "3. 😴 수면에 문제가 있었나요? (잠이 너무 많거나 너무 적음)", "4. 😩 피곤하거나 기운이 없다고 느낀 적이 있었나요?", "5. 🍽️ 식욕이 줄었거나 지나치게 늘었던 적이 있었나요?", "6. 💔 스스로가 실패자라고 느끼거나 자신과 가족을 실망시켰다고 느낀 적이 있었나요?", "7. 🤯 집중하는 데 어려움이 있었나요? (예: 책 읽기, TV 시청 등)", "8. 🌀 너무 느리거나, 반대로 안절부절못한 적이 있었나요?", "9. ⚠️ 죽고 싶다는 생각이나 자해를 고민한 적이 있었나요?"])]

# --- API 라우트 정의 ---
@app.route('/')
def index():
    return render_template('index.html')

# --- 사용자 인증 라우트 (회원가입) ---
@app.route('/register', methods=['POST'])
def register():
    conn = None
    try:
        data = request.json
        username, password = data.get('username'), data.get('password')
        if not username or not password:
            return jsonify({"success": False, "message": "아이디와 비밀번호를 모두 입력해주세요."}), 400
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user:
            return jsonify({"success": False, "message": "이미 존재하는 아이디입니다."}), 409
            
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password, name, birthdate, gender, region_si_do, region_gu) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (username, hashed_password, data.get('name'), data.get('birthdate'), data.get('gender'), data.get('region_si_do'), data.get('region_gu')))
        conn.commit()
    except Exception as e:
        print(f"회원가입 중 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": "회원가입 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()
    return jsonify({"success": True, "message": "회원가입이 완료되었습니다."})

# --- 사용자 인증 라우트 (로그인) ---
@app.route('/login', methods=['POST'])
def login():
    conn = None
    try:
        data = request.json
        username, password = data.get('username'), data.get('password')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    except Exception as e:
        print(f"로그인 DB 조회 중 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": "로그인 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

    if user and check_password_hash(user['password'], password):
        return jsonify({"success": True, "message": "로그인 성공!"})
    else:
        return jsonify({"success": False, "message": "아이디 또는 비밀번호가 일치하지 않습니다."}), 401

# --- 데이터 관리 라우트 (조회) ---
@app.route('/get_data', methods=['GET'])
def get_data():
    conn = None
    try:
        username = request.args.get('username')
        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            return jsonify({"success": False, "message": "사용자를 찾을 수 없습니다."}), 404
            
        records = conn.execute('SELECT id, date, score, status, text, recommended_challenges_json, feedback_given_json FROM records WHERE user_id = ? ORDER BY date ASC', (user['id'],)).fetchall()
        data_list = [dict(row) for row in records]
    except Exception as e:
        print(f"데이터 조회 중 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": "데이터 조회 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()
    return jsonify({"success": True, "data": data_list})

# --- 데이터 관리 라우트 (분석 및 저장) ---
@app.route('/analyze', methods=['POST'])
def analyze_emotion_route():
    conn = None
    try:
        data = request.json
        username = data.get('username')
        mood = data.get('mood')
        sleep = data.get('sleep')
        activity = data.get('activity')
        feeling_text = data.get('feeling_text')

        if not all([username, mood is not None, sleep is not None, activity is not None]):
            return jsonify({"success": False, "message": "필수 입력값이 누락되었습니다."}), 400

        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            return jsonify({"success": False, "message": "로그인 정보가 유효하지 않습니다."}), 401

        # 점수 계산 및 감정 분석 (수정된 calculate_total_score 사용)
        combined_score, text_emotion, breakdown = calculate_total_score(mood, sleep, activity, feeling_text)
        emotion_status = classify_emotion_by_combined_score(combined_score)
        dynamic_challenges = get_dynamic_challenges(mood, sleep, activity, feeling_text)

        # DB 저장용 데이터
        new_record_data = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "score": round(combined_score, 2),
            "status": emotion_status,
            "text": feeling_text,
            "recommended_challenges_json": json.dumps(dynamic_challenges, ensure_ascii=False),
            "feedback_given_json": json.dumps({})
        }
        
        cursor = conn.cursor()
        cursor.execute('INSERT INTO records (user_id, date, score, status, text, recommended_challenges_json, feedback_given_json) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (user['id'], new_record_data['date'], new_record_data['score'], new_record_data['status'], new_record_data['text'], new_record_data['recommended_challenges_json'], new_record_data['feedback_given_json']))
        record_id = cursor.lastrowid
        conn.commit()
        
        # 응답 데이터 생성
        response_data = {
            "success": True, 
            "record_id": record_id, 
            "score": new_record_data['score'], 
            "text_emotion": text_emotion, 
            "emotion_status": emotion_status, 
            "challenges": dynamic_challenges,
            "breakdown": breakdown
        }
    except Exception as e:
        print(f"분석 처리 중 오류: {e}")
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"success": False, "message": "분석 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()
    return jsonify(response_data)

# --- 피드백 처리 라우트 ---
@app.route('/feedback', methods=['POST'])
def handle_feedback():
    conn = None
    try:
        data = request.json
        username = data.get('username')
        record_id = data.get('record_id')
        challenge_title = data.get('challenge_title')
        rating = data.get('rating')

        if not all([username, record_id, challenge_title, rating is not None]):
            return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."}), 400

        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            return jsonify({"success": False, "message": "사용자를 찾을 수 없습니다."}), 404

        user_id = user['id']
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 피드백 테이블에 저장
        conn.execute("INSERT INTO challenge_feedback (user_id, record_id, challenge_title, rating, timestamp) VALUES (?, ?, ?, ?, ?)", 
                     (user_id, record_id, challenge_title, rating, timestamp))
        
        # 기록 테이블의 피드백 JSON 업데이트
        record = conn.execute("SELECT feedback_given_json FROM records WHERE id = ? AND user_id = ?", (record_id, user_id)).fetchone()
        if record:
             current_feedback_json = record['feedback_given_json']
             feedback_given = json.loads(current_feedback_json) if current_feedback_json else {}
             feedback_given[challenge_title] = rating
             conn.execute("UPDATE records SET feedback_given_json = ? WHERE id = ?", 
                          (json.dumps(feedback_given, ensure_ascii=False), record_id))
             conn.commit()
        else:
             conn.rollback()
             return jsonify({"success": False, "message": "해당 기록을 찾을 수 없습니다."}), 404
             
    except Exception as e:
        print(f"피드백 저장 중 오류 발생: {e}")
        print(traceback.format_exc())
        if conn: conn.rollback()
        return jsonify({"success": False, "message": "피드백 저장 중 오류가 발생했습니다."}), 500
    finally:
         if conn: conn.close()
    return jsonify({"success": True, "message": "피드백이 저장되었습니다."})

# --- 챗봇 라우트 ---
@app.route('/chatbot/start', methods=['GET'])
def chatbot_start():
    return jsonify({"questions": PHQ9_QUESTIONS})

@app.route('/chatbot/result', methods=['POST'])
def chatbot_result():
    data = request.json
    total_score = sum(data.get('answers', []))
    suicidal_thoughts = len(data.get('answers', [])) == 9 and data['answers'][8] > 0
    
    if total_score <= 4:
        result_message = f"총점 {total_score}점. 정상 범위이며 우울 증상이 거의 없습니다."
    elif total_score <= 9:
        result_message = f"총점 {total_score}점. 가벼운 수준의 우울 증상이 의심됩니다."
    elif total_score <= 14:
        result_message = f"총점 {total_score}점. 중간 수준의 우울 증상이 의심됩니다. 전문가와의 상담을 고려해 보세요."
    elif total_score <= 19:
        result_message = f"총점 {total_score}점. 중증 수준의 우울 증상이 의심됩니다. 전문가의 도움이 필요합니다."
    else:
        result_message = f"총점 {total_score}점. 심한 수준의 우울 증상이 의심됩니다. 빠른 시일 내에 전문가의 도움이 필요합니다."
        
    hospital_info = None
    if suicidal_thoughts:
        result_message += "\n\n특히 마지막 문항 응답으로 보아 전문가의 도움이 시급할 수 있습니다. 즉시 상담하시기를 강력히 권고합니다."
        hospital_info = "정신건강위기상담전화 (📞1577-0199, 24시간), 보건복지부 희망의 전화 (📞129)"
    elif total_score > 14:
        hospital_info = "가까운 정신건강의학과나 정신건강복지센터에 방문하여 상담받아보세요."
        
    return jsonify({"total_score": total_score, "message": result_message, "hospital_info": hospital_info})

# --- 데이터베이스 스키마 정의 ---
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    username TEXT UNIQUE NOT NULL, 
    password TEXT NOT NULL, 
    name TEXT, 
    birthdate TEXT, 
    gender TEXT, 
    region_si_do TEXT, 
    region_gu TEXT
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    user_id INTEGER NOT NULL, 
    date TEXT NOT NULL, 
    score REAL NOT NULL, 
    status TEXT NOT NULL, 
    text TEXT, 
    recommended_challenges_json TEXT, 
    feedback_given_json TEXT, 
    FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS challenge_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    user_id INTEGER NOT NULL, 
    record_id INTEGER NOT NULL, 
    challenge_title TEXT NOT NULL, 
    rating INTEGER NOT NULL, 
    timestamp TEXT NOT NULL, 
    FOREIGN KEY (user_id) REFERENCES users (id), 
    FOREIGN KEY (record_id) REFERENCES records (id)
);
"""

# --- 서버 실행 ---
if __name__ == '__main__':
    conn = None
    try:
        # 서버 시작 시 DB 스키마 확인 및 생성
        conn = get_db_connection()
        conn.executescript(SCHEMA)
        conn.commit()
    except Exception as e:
        print(f"데이터베이스 초기화 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        if conn: conn.close()
    app.run(debug=True)