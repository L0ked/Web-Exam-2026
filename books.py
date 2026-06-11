from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from db import get_db_connection
from utils import check_roles
import bleach
import markdown
import os
import hashlib
import math

books_bp = Blueprint('books', __name__)

@books_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as count FROM books")
    total_books = cursor.fetchone()['count']
    total_pages = math.ceil(total_books / per_page)

    query = """
        SELECT b.*,
               (SELECT GROUP_CONCAT(g.name SEPARATOR ', ') 
                FROM book_genre bg JOIN genres g ON bg.genre_id = g.id 
                WHERE bg.book_id = b.id) as genres,
               (SELECT COUNT(r.id) FROM reviews r WHERE r.book_id = b.id AND r.status_id = 2) as reviews_count,
               (SELECT AVG(r.rating) FROM reviews r WHERE r.book_id = b.id AND r.status_id = 2) as avg_rating,
               (SELECT c.file_name FROM covers c WHERE c.book_id = b.id LIMIT 1) as cover_file
        FROM books b
        ORDER BY b.year DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, (per_page, offset))
    books = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return render_template('index.html', books=books, page=page, total_pages=total_pages)

@books_bp.route('/book/<int:book_id>')
def show(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()
    
    if not book:
        flash("Книга не найдена", "danger")
        return redirect(url_for('books.index'))
        
    cursor.execute("SELECT * FROM covers WHERE book_id = %s", (book_id,))
    cover = cursor.fetchone()
    
    cursor.execute("""
        SELECT g.name FROM genres g
        JOIN book_genre bg ON g.id = bg.genre_id
        WHERE bg.book_id = %s
    """, (book_id,))
    genres = [row['name'] for row in cursor.fetchall()]
    
    cursor.execute("""
        SELECT r.*, u.first_name, u.last_name, u.middle_name 
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = %s AND r.status_id = 2
        ORDER BY r.created_at DESC
    """, (book_id,))
    reviews = cursor.fetchall()

    cursor.close()
    conn.close()
    
    book['html_description'] = markdown.markdown(book['short_description'])
    
    for r in reviews:
        r['html_text'] = markdown.markdown(r['text'])

    return render_template('book.html', book=book, cover=cover, genres=genres, reviews=reviews)

import logging
# Add to the top of books.py
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inside create()
@books_bp.route('/book/new', methods=['GET', 'POST'])
@login_required
@check_roles(1)
def create():
    logger.info("Entering create book")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        logger.info("Received POST request")
        title = request.form.get('title')
        short_description = request.form.get('short_description')
        year = request.form.get('year')
        publisher = request.form.get('publisher')
        author = request.form.get('author')
        pages = request.form.get('pages')
        genre_ids = request.form.getlist('genres')
        cover_file = request.files.get('cover')
        
        logger.info("Starting sanitization")
        sanitized_description = bleach.clean(short_description)
        logger.info("Finished sanitization")

        try:
            cursor.execute("""
                INSERT INTO books (title, short_description, year, publisher, author, pages)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title, sanitized_description, year, publisher, author, pages))
            
            book_id = cursor.lastrowid
            
            for genre_id in genre_ids:
                cursor.execute("INSERT INTO book_genre (book_id, genre_id) VALUES (%s, %s)", (book_id, genre_id))
            
            if cover_file and cover_file.filename != '':
                file_content = cover_file.read()
                md5_hash = hashlib.md5(file_content).hexdigest()
                
                cursor.execute("SELECT id, file_name FROM covers WHERE md5_hash = %s", (md5_hash,))
                existing_cover = cursor.fetchone()
                
                mime_type = cover_file.mimetype
                
                if existing_cover:
                    cursor.execute("""
                        INSERT INTO covers (file_name, mime_type, md5_hash, book_id)
                        VALUES (%s, %s, %s, %s)
                    """, (existing_cover['file_name'], mime_type, md5_hash, book_id))
                else:
                    ext = os.path.splitext(cover_file.filename)[1]
                    cursor.execute("""
                        INSERT INTO covers (file_name, mime_type, md5_hash, book_id)
                        VALUES (%s, %s, %s, %s)
                    """, ('temp', mime_type, md5_hash, book_id))
                    
                    cover_id = cursor.lastrowid
                    new_filename = f"{cover_id}{ext}"
                    
                    cursor.execute("UPDATE covers SET file_name = %s WHERE id = %s", (new_filename, cover_id))
                    
                    cover_path = os.path.join(current_app.config['UPLOAD_FOLDER'], new_filename)
                    with open(cover_path, 'wb') as f:
                        f.write(file_content)

            conn.commit()
            flash("Книга успешно добавлена", "success")
            return redirect(url_for('books.show', book_id=book_id))
        except Exception as e:
            import traceback
            print("ERROR DURING CREATE:", e)
            print("TRACEBACK:", traceback.format_exc())
            print("FORM DATA:", request.form)
            print("FILES:", request.files)
            conn.rollback()
            flash(f"При сохранении данных возникла ошибка: {str(e)}", "danger")
            # fallback to render template with form data
        finally:
            cursor.close()
            conn.close()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM genres")
    all_genres = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('book_form.html', genres=all_genres, book={}, selected_genres=[])

@books_bp.route('/book/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
@check_roles(1, 2)
def edit(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        title = request.form.get('title')
        short_description = request.form.get('short_description')
        year = request.form.get('year')
        publisher = request.form.get('publisher')
        author = request.form.get('author')
        pages = request.form.get('pages')
        genre_ids = request.form.getlist('genres')
        
        sanitized_description = bleach.clean(short_description)

        try:
            cursor.execute("""
                UPDATE books 
                SET title=%s, short_description=%s, year=%s, publisher=%s, author=%s, pages=%s
                WHERE id=%s
            """, (title, sanitized_description, year, publisher, author, pages, book_id))
            
            cursor.execute("DELETE FROM book_genre WHERE book_id = %s", (book_id,))
            for genre_id in genre_ids:
                cursor.execute("INSERT INTO book_genre (book_id, genre_id) VALUES (%s, %s)", (book_id, genre_id))
            
            conn.commit()
            flash("Книга успешно обновлена", "success")
            return redirect(url_for('books.show', book_id=book_id))
        except Exception as e:
            conn.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
        finally:
            cursor.close()
            conn.close()
            
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()
    cursor.execute("SELECT genre_id FROM book_genre WHERE book_id = %s", (book_id,))
    selected_genres = [row['genre_id'] for row in cursor.fetchall()]
    cursor.execute("SELECT * FROM genres")
    all_genres = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not book:
        return redirect(url_for('books.index'))
        
    return render_template('book_form.html', genres=all_genres, book=book, selected_genres=selected_genres, is_edit=True)

@books_bp.route('/book/<int:book_id>/delete', methods=['POST'])
@login_required
@check_roles(1)
def delete(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT file_name FROM covers WHERE book_id = %s", (book_id,))
        covers = cursor.fetchall()
        
        cursor.execute("SELECT title FROM books WHERE id = %s", (book_id,))
        book = cursor.fetchone()
        
        if book:
            cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
            conn.commit()
            
            for cover in covers:
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], cover['file_name'])
                if os.path.exists(file_path):
                    # Check if any other cover record uses the same file_name before deleting physically
                    cursor.execute("SELECT COUNT(*) as count FROM covers WHERE file_name = %s", (cover['file_name'],))
                    if cursor.fetchone()['count'] == 0:
                        os.remove(file_path)

            flash(f"Книга '{book['title']}' успешно удалена", "success")
    except Exception as e:
        conn.rollback()
        flash("Ошибка при удалении книги", "danger")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('books.index'))
