import os
import mysql.connector
import hashlib
import urllib.request
from urllib.error import URLError
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

def download_cover(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read(), response.info().get_content_type()
    except URLError as e:
        print(f"Failed to download {url}: {e}")
        return b"", "image/jpeg"

def init_db():
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', '')
    )
    cursor = conn.cursor(dictionary=True)
    
    # Create DB if not exists
    cursor.execute("CREATE DATABASE IF NOT EXISTS library_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute("USE library_db")
    
    with open('schema.sql', 'r', encoding='utf-8') as f:
        sql_commands = f.read().split(';')
        
    for command in sql_commands:
        if command.strip():
            try:
                cursor.execute(command)
            except mysql.connector.Error as err:
                pass # Already exists or similar non-critical error during init

    # Insert users
    users = [
        ('admin', 'adminpass', 'Иванов', 'Иван', 'Иванович', 1),
        ('mod', 'modpass', 'Петров', 'Петр', 'Петрович', 2),
        ('user', 'userpass', 'Сидоров', 'Сидор', 'Сидорович', 3)
    ]
    
    for user in users:
        try:
            cursor.execute("SELECT id FROM users WHERE login = %s", (user[0],))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (login, password_hash, last_name, first_name, middle_name, role_id) VALUES (%s, %s, %s, %s, %s, %s)",
                               (user[0], generate_password_hash(user[1]), user[2], user[3], user[4], user[5]))
        except mysql.connector.Error as err:
            pass
            
    conn.commit()
    
    # Seed data
    cursor.execute("SELECT COUNT(*) as count FROM books")
    if cursor.fetchone()['count'] == 0:
        print("Database is empty. Seeding realistic books...")
        
        books_data = [
            {
                "title": "Мастер и Маргарита",
                "short_description": "Знаменитый роман Михаила Булгакова. В нем переплетаются мистика, сатира на советское общество 1930-х годов и глубокая философия.\n\n**Главные темы:**\n* Добро и зло\n* Истинная любовь\n* Творческая свобода",
                "year": 1967,
                "publisher": "YMCA-Press",
                "author": "Михаил Булгаков",
                "pages": 480,
                "genres": ["Роман", "Фантастика"],
                "cover_url": "https://covers.openlibrary.org/b/id/13214532-L.jpg"
            },
            {
                "title": "Пикник на обочине",
                "short_description": "Одно из самых известных произведений братьев Стругацких. Зона Отчуждения, сталкеры, смертельные артефакты и вечный вопрос о смысле человеческого существования в равнодушной Вселенной.",
                "year": 1972,
                "publisher": "Аврора",
                "author": "Аркадий и Борис Стругацкие",
                "pages": 256,
                "genres": ["Фантастика", "Приключения"],
                "cover_url": "https://covers.openlibrary.org/b/id/8316315-L.jpg"
            },
            {
                "title": "Собачье сердце",
                "short_description": "Сатирическая повесть об эксперименте профессора Преображенского по пересадке человеческого гипофиза собаке. Гениальное предвидение последствий социального эксперимента в России.\n\n> *«Разруха не в клозетах, а в головах!»*",
                "year": 1968,
                "publisher": "Студенческий меридиан",
                "author": "Михаил Булгаков",
                "pages": 160,
                "genres": ["Фантастика"],
                "cover_url": "https://covers.openlibrary.org/b/id/11195610-L.jpg"
            },
            {
                "title": "Трудно быть богом",
                "short_description": "Землянин Антон (дон Румата) находится на планете Арканар, живущей по законам мрачного Средневековья. Он должен наблюдать за историческим процессом, но как остаться безучастным, когда льется кровь?",
                "year": 1964,
                "publisher": "Молодая гвардия",
                "author": "Аркадий и Борис Стругацкие",
                "pages": 320,
                "genres": ["Фантастика", "Роман", "Приключения"],
                "cover_url": "https://covers.openlibrary.org/b/id/14588232-L.jpg"
            }
        ]

        cursor.execute("SELECT id, name FROM genres")
        genres_map = {row['name']: row['id'] for row in cursor.fetchall()}
        
        os.makedirs(os.path.join('static', 'covers'), exist_ok=True)

        for book in books_data:
            print(f"Seeding book: {book['title']}...")
            
            cursor.execute("""
                INSERT INTO books (title, short_description, year, publisher, author, pages)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (book['title'], book['short_description'], book['year'], book['publisher'], book['author'], book['pages']))
            book_id = cursor.lastrowid
            
            for genre_name in book['genres']:
                if genre_name in genres_map:
                    cursor.execute("INSERT INTO book_genre (book_id, genre_id) VALUES (%s, %s)", (book_id, genres_map[genre_name]))
            
            # Download and save cover
            file_content, mime_type = download_cover(book['cover_url'])
            if file_content:
                md5_hash = hashlib.md5(file_content).hexdigest()
                ext = '.jpg'
                
                cursor.execute("""
                    INSERT INTO covers (file_name, mime_type, md5_hash, book_id)
                    VALUES (%s, %s, %s, %s)
                """, ('temp', mime_type, md5_hash, book_id))
                
                cover_id = cursor.lastrowid
                new_filename = f"{cover_id}{ext}"
                
                cursor.execute("UPDATE covers SET file_name = %s WHERE id = %s", (new_filename, cover_id))
                
                cover_path = os.path.join('static', 'covers', new_filename)
                with open(cover_path, 'wb') as f:
                    f.write(file_content)

            # Add an approved review
            cursor.execute("""
                INSERT INTO reviews (book_id, user_id, rating, text, status_id)
                VALUES (%s, %s, %s, %s, 2)
            """, (book_id, 3, 5, f"Отличная книга **{book['title']}**, всем настоятельно рекомендую к прочтению!"))

        conn.commit()
        print("Seeding completed!")
    else:
        print("Database already contains books. Skipping seed.")

    cursor.close()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
