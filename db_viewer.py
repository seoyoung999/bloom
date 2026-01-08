import sqlite3
import os

DATABASE_FILE = 'database.db'

def view_database():
    """
    database.db 파일의 모든 내용을 읽어서 터미널에 출력합니다.
    """
    if not os.path.exists(DATABASE_FILE):
        print(f"'{DATABASE_FILE}' 파일을 찾을 수 없습니다.")
        print("먼저 app.py를 실행하여 데이터베이스를 생성하고 데이터를 추가해주세요.")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 30)
    print("        USERS 테이블 내용")
    print("=" * 30)
    try:
        users = cursor.execute("SELECT id, username, name, birthdate, gender FROM users").fetchall()
        if not users:
            print("사용자 정보가 없습니다.")
        else:
            for user in users:
                print(f"ID: {user['id']}, 아이디: {user['username']}, 이름: {user['name']}, 생년월일: {user['birthdate']}, 성별: {user['gender']}")
    except sqlite3.OperationalError:
        print("users 테이블을 찾을 수 없습니다.")
    
    print("\n" + "=" * 30)
    print("       RECORDS 테이블 내용")
    print("=" * 30)
    try:
        records = cursor.execute("SELECT id, user_id, date, score, status, text FROM records ORDER BY date").fetchall()
        if not records:
            print("감정 기록이 없습니다.")
        else:
            for record in records:
                print(f"ID: {record['id']}, 사용자ID: {record['user_id']}, 날짜: {record['date']}, 점수: {record['score']}, 상태: {record['status']}")
                print(f"  └ 텍스트: {record['text']}")
    except sqlite3.OperationalError:
        print("records 테이블을 찾을 수 없습니다.")

    conn.close()
    print("\n" + "=" * 30)

if __name__ == '__main__':
    view_database()