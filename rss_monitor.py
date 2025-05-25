#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import flask
from flask import Flask, request, jsonify, render_template_string
import feedparser
from datetime import datetime
import sqlite3
import threading
import time
import atexit


app = Flask(__name__)

#  БД
def init_db():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rss_sources
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  url TEXT UNIQUE,
                  last_checked TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS keywords
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  word TEXT UNIQUE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS news_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT,
                  description TEXT,
                  link TEXT UNIQUE,
                  source TEXT,
                  found_keywords TEXT,
                  published TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Проверка RSS-лент
def check_feeds():
    while True:
        try:
            conn = sqlite3.connect('rss_monitor.db')
            c = conn.cursor()
            
            # Получаем источники и ключевые слова
            c.execute("SELECT url FROM rss_sources")
            sources = [row[0] for row in c.fetchall()]
            
            c.execute("SELECT word FROM keywords")
            keywords = [row[0].lower() for row in c.fetchall()]
            
            for url in sources:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    content = f"{entry.title} {getattr(entry, 'description', '')}".lower()
                    found_kws = [kw for kw in keywords if kw in content]
                    
                    if found_kws:
                        try:
                            c.execute("INSERT OR IGNORE INTO news_items VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                                    (entry.title,
                                     getattr(entry, 'description', ''),
                                     entry.link,
                                     url,
                                     ', '.join(found_kws),
                                     datetime.now().isoformat()))
                            print(f"Found news: {entry.title} | Keywords: {', '.join(found_kws)}")
                        except sqlite3.IntegrityError:
                            pass
                
                # Обновляем время последней проверки
                c.execute("UPDATE rss_sources SET last_checked = ? WHERE url = ?",
                         (datetime.now().isoformat(), url))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error in feed checking: {e}")
        
        time.sleep(1800)  # Проверка каждый час

# Запуск фонового потока
checker_thread = threading.Thread(target=check_feeds)
checker_thread.daemon = True
checker_thread.start()

# Главный маршрут
@app.route('/')
def index():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    c.execute("SELECT * FROM news_items ORDER BY published DESC")
    news = c.fetchall()
    conn.close()
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head><title>RSS Monitor</title></head>
        <body>
            <h1>News</h1>
            {% for item in news %}
            <div style="margin-bottom: 20px;">
                <h3><a href="{{ item[3] }}">{{ item[1] }}</a></h3>
                <p>{{ item[2] }}</p>
                <small>Keywords: {{ item[5] }}</small>
            </div>
            {% endfor %}
        </body>
        </html>
    ''', news=news)

@app.route('/api/news', methods=['GET'])
def get_news():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    c.execute("SELECT * FROM news_items ORDER BY published DESC")
    news = [{
        'id': row[0],
        'title': row[1],
        'description': row[2],
        'link': row[3],
        'source': row[4],
        'keywords': row[5],
        'published': row[6]
    } for row in c.fetchall()]
    conn.close()
    return jsonify(news)

@app.route('/api/sources', methods=['GET', 'POST'])
def manage_sources():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        try:
            c.execute("INSERT INTO rss_sources (url, last_checked) VALUES (?, ?)",
                      (url, datetime.now().isoformat()))
            conn.commit()
            return jsonify({'message': 'Source added'}), 201
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Source already exists'}), 400
    
    c.execute("SELECT * FROM rss_sources")
    sources = [{'id': row[0], 'url': row[1], 'last_checked': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(sources)

@app.route('/api/keywords', methods=['GET', 'POST', 'DELETE'])
def manage_keywords():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        word = request.json.get('word')
        if not word:
            return jsonify({'error': 'Keyword is required'}), 400
        
        try:
            c.execute("INSERT INTO keywords (word) VALUES (?)", (word,))
            conn.commit()
            return jsonify({'message': 'Keyword added'}), 201
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Keyword already exists'}), 400
    
    elif request.method == 'DELETE':
        word = request.json.get('word')
        if not word:
            return jsonify({'error': 'Keyword is required'}), 400
        
        c.execute("DELETE FROM keywords WHERE word = ?", (word,))
        conn.commit()
        return jsonify({'message': 'Keyword deleted'})
    
    c.execute("SELECT * FROM keywords")
    keywords = [{'id': row[0], 'word': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(keywords)


def add_sample_data():
    conn = sqlite3.connect('rss_monitor.db')
    c = conn.cursor()
    
    # Добавляем тестовые RSS-источники
    sample_sources = [
        'https://meduza.io/rss2/medical',
        'https://lenta.ru/rss/news/med',
        'https://ria.ru/export/rss2/health/index.xml',
        'https://nplus1.ru/rss',
        'https://elementy.ru/rss/news',
        'https://habr.com/ru/rss/hub/science/?fl=ru'
    ]
    
    for url in sample_sources:
        try:
            c.execute("INSERT OR IGNORE INTO rss_sources (url) VALUES (?)", (url,))
        except:
            pass
    
    # Rлючевые слова
    sample_keywords = [ 'здоровье', 'медицина', 'больница', 'врач', 
    'лечение', 'вакцина', 'вирус', 'эпидемия',
    'COVID', 'грипп', 'диагноз', 'терапия',
    'пациент', 'клиника', 'анализ', 'рецепт', 'исследование', 'открытие', 'ученые', 'лаборатория',
    'технология', 'инновации', 'эксперимент', 'космос',
    'биология', 'физика', 'химия', 'генетика',
    'искусственный интеллект', 'робот', 'нанотехнологии']
    
    for word in sample_keywords:
        try:
            c.execute("INSERT OR IGNORE INTO keywords (word) VALUES (?)", (word,))
        except:
            pass
    
    conn.commit()
    conn.close()

add_sample_data()

if __name__ == '__main__':
    app.run(debug=True)

