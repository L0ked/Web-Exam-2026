from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from db import get_db_connection
from utils import check_roles
import bleach
import markdown
import math

reviews_bp = Blueprint('reviews', __name__)

@reviews_bp.route('/book/<int:book_id>/review', methods=['GET', 'POST'])
@login_required
@check_roles(1, 2, 3)
def create(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id FROM reviews WHERE book_id = %s AND user_id = %s", (book_id, current_user.id))
    existing_review = cursor.fetchone()
    if existing_review:
        flash("Вы уже оставили рецензию на эту книгу.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for('books.show', book_id=book_id))

    if request.method == 'POST':
        rating = request.form.get('rating')
        text = request.form.get('text')
        sanitized_text = bleach.clean(text)
        
        try:
            # 1: На рассмотрении
            cursor.execute("""
                INSERT INTO reviews (book_id, user_id, rating, text, status_id)
                VALUES (%s, %s, %s, %s, 1)
            """, (book_id, current_user.id, rating, sanitized_text))
            conn.commit()
            flash("Ваша рецензия отправлена на модерацию", "success")
            return redirect(url_for('books.show', book_id=book_id))
        except Exception as e:
            conn.rollback()
            flash("Произошла ошибка при сохранении рецензии", "danger")
        finally:
            cursor.close()
            conn.close()

    cursor.execute("SELECT title FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return render_template('review_form.html', book=book, book_id=book_id)

@reviews_bp.route('/my_reviews')
@login_required
def my_reviews():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT r.*, b.title as book_title, s.name as status_name 
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN review_statuses s ON r.status_id = s.id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """, (current_user.id,))
    reviews = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    for r in reviews:
        r['html_text'] = markdown.markdown(r['text'])
        
    return render_template('my_reviews.html', reviews=reviews)

@reviews_bp.route('/moderate_reviews')
@login_required
@check_roles(2)
def moderate():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM reviews WHERE status_id = 1")
    total_reviews = cursor.fetchone()['count']
    total_pages = math.ceil(total_reviews / per_page)
    
    cursor.execute("""
        SELECT r.*, b.title as book_title, u.first_name, u.last_name, u.middle_name 
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN users u ON r.user_id = u.id
        WHERE r.status_id = 1
        ORDER BY r.created_at ASC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    reviews = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('moderate_reviews.html', reviews=reviews, page=page, total_pages=total_pages)

@reviews_bp.route('/review/<int:review_id>/view')
@login_required
@check_roles(2)
def view_review(review_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT r.*, b.title as book_title, u.first_name, u.last_name, u.middle_name 
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN users u ON r.user_id = u.id
        WHERE r.id = %s AND r.status_id = 1
    """, (review_id,))
    review = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not review:
        flash("Рецензия не найдена или уже рассмотрена", "warning")
        return redirect(url_for('reviews.moderate'))
        
    review['html_text'] = markdown.markdown(review['text'])
        
    return render_template('moderate_review.html', review=review)

@reviews_bp.route('/review/<int:review_id>/<action>', methods=['POST'])
@login_required
@check_roles(2)
def process_review(review_id, action):
    if action not in ['approve', 'reject']:
        return redirect(url_for('reviews.moderate'))
        
    status_id = 2 if action == 'approve' else 3
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE reviews SET status_id = %s WHERE id = %s", (status_id, review_id))
        conn.commit()
        flash("Рецензия успешно обработана", "success")
    except Exception as e:
        conn.rollback()
        flash("Ошибка при обработке рецензии", "danger")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('reviews.moderate'))
