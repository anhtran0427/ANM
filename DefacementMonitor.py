from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory
from flask_apscheduler import APScheduler
import requests
from bs4 import BeautifulSoup
import hashlib
import os
import json
import difflib
from selenium import webdriver
from PIL import Image, ImageChops
import io
from datetime import datetime
from time import sleep
from flask_mail import Mail, Message
import uuid 
from db import service
from pathlib import Path, PureWindowsPath
import re

app = Flask(__name__)
app.secret_key = 'supersecretkey'
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Global variables
PUSHOVER_USER_MAIL = ''
urls=[]
url = {}
custom_message = ''
previous_hashes = {}
previous_contents = {}
previous_screenshots = {}
previous_domtree={}
last_checks = {}
config_file = 'config.json'
last_checks_file = 'last_checks.json'
backup_file='backup.json'
html_code=''


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'defacemonitor@gmail.com'  # Use your actual Gmail address
app.config['MAIL_PASSWORD'] = 'vqugmqtomfqgpyoz'     # Use your generated App Password
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

def send_pushover_notification(url, report_filename, screenshot_filename):
    with app.app_context():
        msg = Message(
            subject='Deface Monitored!', 
            sender='defacemonitor@gmail.com',  # Ensure this matches MAIL_USERNAME
            recipients=PUSHOVER_USER_MAIL  # Replace with actual recipient's email
        )
        msg.body = f"Changes detected on {url}. Report: {report_filename}, Screenshot: {screenshot_filename}"
        
        with app.open_resource(f"{report_filename}") as fp:
            msg.attach(f"{report_filename}", "text/plain", fp.read())

        mail.send(msg)
        return "Message sent!"

def get_page_content(url):
    response = requests.get(url)
    return response.text

def get_page_hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def get_detailed_changes(old_content, new_content):
    differ = difflib.Differ()
    diff = list(differ.compare(old_content.splitlines(), new_content.splitlines()))
    return "\n".join(diff)

def take_screenshot(url):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1920, 1080)  # Set a standard size
    driver.get(url)
    screenshot = driver.get_screenshot_as_png()
    driver.quit()
    return Image.open(io.BytesIO(screenshot))

def compare_screenshots(old_screenshot, new_screenshot):
    diff = ImageChops.difference(old_screenshot, new_screenshot)
    return diff.getbbox() is not None

def is_significant_change(old_content, new_content):
    for pattern in ignore_patterns:
        if pattern in old_content or pattern in new_content:
            return False
    diff_ratio = difflib.SequenceMatcher(None, old_content, new_content).ratio()
    print("diff", diff_ratio)
    return (1 - diff_ratio) > change_threshold

def load_last_checks():
    global last_checks
    if os.path.exists(last_checks_file):
        with open(last_checks_file, 'r') as f:
            last_checks = json.load(f)
    else:
        last_checks = {}

def save_last_checks():
    with open(last_checks_file, 'w') as f:
        json.dump(last_checks, f)

def bfs_tree(tag):
    string=""
    queue_=[]
    queue_.append(tag)
    while queue_:
        tag=queue_.pop(0)
        if tag.children:
            ind=0
            for child in tag.findChildren(recursive=False):  # recursive = False b/c otherwise, it messes things up  # if there are kids, add the child name which has kids, then add the tree to it
                if child.has_attr('class'):
                    child['class'].append(str(ind))
                    if 'dynamic' in child['class']:
                        string += trace(child)+"\n"
                else:
                    child['class'] = [str(ind)]
                ind=ind+1
                if child.findChildren:
                    queue_.append(child)
    return string

def trace(tag):
    if tag is None:
        return ""
    string=""
    string+=tag['class'][-1]+"."
    for parent in tag.parents :
        if parent.name=="body":
            break
        string+=parent['class'][-1]+"."
    return string

def retrace(tag,dir):
    if dir=="":
        return None
    dirs=dir.split('.')
    if not dirs:
        return None
    dirs.pop()
    for childInd in reversed(dirs):
        if tag is not None:
            tag=tag.findChildren(attrs={'class': str(childInd)},recursive=False)[0]
    return tag

def check_for_changes(Id):
        url_=service.get_url(Id)
        url=url_["URL"]
        print(urls)
        print("check_for_change")
        new_content = get_page_content(url)
        new_soup = BeautifulSoup(new_content, 'html5lib')
        bfs_tree(new_soup.find('body'))
        if url not in previous_domtree:
            setup_dynamic(url_)
        dynamic_elements = previous_domtree[url].split('\n')
        for ele in dynamic_elements:
            tag = retrace(new_soup.body, ele)
            if tag is not None:
                tag.decompose()

        new_content = str(new_soup)
        new_hash = get_page_hash(new_content)
        new_screenshot = take_screenshot(url)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_checks[url] = current_time

        save_last_checks()

        report_filename = f"report_{re.sub('[^a-zA-Z0-9_]', '_', url)}.txt"
        screenshot_filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url)}.png"



        new_screenshot.save(os.path.join('screenshots',screenshot_filename))
        report_filename=os.path.join('reports',report_filename)
        if url not in previous_hashes:
            previous_hashes[url] = new_hash
            previous_contents[url] = new_content

            with open(report_filename, "w") as f:
                f.write(f"Initial check for {url} at {current_time}\n")
                f.write("No previous content to compare.\n\n")
            return

        with open(report_filename, "a") as f:
            f.write(f"\nCheck performed for {url} at {current_time}\n")
            if new_hash != previous_hashes[url]:
                changes = get_detailed_changes(previous_contents[url], new_content)
                f.write("Changes detected:\n")
                f.write(changes)
                f.write("\n")
            else:
                f.write("No significant changes detected.\n\n")
        print("OK")
        previous_hashes[url] = new_hash
        previous_contents[url] = new_content
        previous_screenshots[url] = new_screenshot

def setup_dynamic(url):
    filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url['URL'])}.html"
    report_path = os.path.join('htmlfiles', filename)
    if not os.path.exists('htmlfiles'):
        os.makedirs('htmlfiles')
    if not os.path.isfile(report_path):
        save_htmlfiles(url)
    with open(report_path, 'r') as file:
        new_content = file.read()
    new_soup = BeautifulSoup(new_content, 'html5lib')
    previous_domtree[url['URL']]=bfs_tree(new_soup.find('body'))
    print(previous_domtree[url['URL']])


def load_config():
    global PUSHOVER_USER_MAIL, urls, custom_message, ignore_patterns,url
    if os.path.exists(config_file):
        with open(config_file, 'r') as file:
            config = json.load(file)
            PUSHOVER_USER_MAIL = config.get('user_mail', '')
            urls = config.get('url', [])
    for e in urls:
        edict=service.add_url(e,0)
        setup_dynamic(edict)

def save_config():
    config = {
        'user_mail': PUSHOVER_USER_MAIL,
        'url': urls,
    }
    with open(config_file, 'w') as file:
        json.dump(config, file)

def save_htmlfiles(url):
    url_literal = url["URL"]
    filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url_literal)}.html"
    report_path = os.path.join('htmlfiles', filename)

    if not os.path.exists('htmlfiles'):
        os.makedirs('htmlfiles')

    with open(report_path, 'w') as f:
        new_content = get_page_content(url_literal)
        soup=BeautifulSoup(new_content, 'html5lib')
        new_content=str(soup.find('body'))
        f.write(new_content)
    setup_dynamic(url)


def clear_by_name(URL):
    global urls, last_checks, previous_domtree, previous_hashes, previous_contents,previous_screenshots
    for ind in range(len(urls)):
        if ind not in range(len(urls)):
            break
        if urls[ind]==URL:
            urls.pop(ind)
    if URL in last_checks:
        del last_checks[URL]
    if URL in previous_domtree:
        del previous_domtree[URL]
    if URL in previous_hashes:
        del previous_hashes[URL]
    if URL in previous_contents:
        del previous_contents[URL]
    if URL in previous_screenshots:
        del previous_screenshots[URL]
    service.clear_url_by_name(URL)

def log_dump():
    global previous_hashes,previous_contents
    backup = {
        'hash': previous_hashes,
        'content': previous_contents,
    }
    with open(backup_file, 'w') as file:
        json.dump(backup, file)

def load_log():
    global previous_hashes,previous_contents
    if os.path.exists(backup_file):
        with open(backup_file, 'r') as file:
            backup = json.load(file)
            previous_hashes=backup.get('hash',{})
            previous_contents=backup.get('content',{})



@app.route('/', methods=['GET', 'POST'])
def index():
    global PUSHOVER_USER_MAIL, urls, custom_message, ignore_patterns
    
    if request.method == 'POST':
        for url in request.form['url'].split(','):
            if url not in urls:
                url = url
                print("url", url)
                service.add_url(url, 0)
        for oldurls in urls:
            if oldurls not in request.form['url'].split(','):
                clear_by_name(oldurls)
        urls=[]
        for url_ in service.get_urls():
            urls.append(url_["URL"])
        PUSHOVER_USER_MAIL = request.form['user_mail']
        ignore_patterns = request.form.getlist('ignore_patterns')

        
        if 'save_config' in request.form:
            save_config()
            flash('Configuration saved!', 'success')
        else:
            flash('Configuration updated but not saved!', 'info')
    URL=""
    for e in urls:
        URL=URL+e+","
    URL=URL[0:-1]
    return render_template('index.html',
                           user_mail = PUSHOVER_USER_MAIL,
                           url=URL,
                           ignore_patterns=ignore_patterns)




@app.route('/start/<string:id>', methods=['POST'])
def start_monitoring(id):
    interval = int(request.form['interval'])
    schedule = request.form['schedule']
    
    if schedule:
        scheduler.add_job(id = id , args=[id], func=check_for_changes, trigger='cron', **cron_to_dict(schedule))
    else:
        scheduler.add_job(id = id ,args=[id], func=check_for_changes, trigger='interval', minutes=interval)
    
    # Run the job once immediately
    # scheduler.add_job(id = id , func=check_for_changes, trigger='date', run_date=datetime.now())
    service.update_url(id, URL=None, status=1)

    flash('Monitoring started!', 'success')
    # Add a small delay to allow the first check to complete
    sleep(2)
    return redirect(url_for('dashboard'))


@app.route('/start_all', methods=['POST'])
def start_all():
    interval = int(request.form['interval'])
    schedule = request.form['schedule']
    for url_ in service.get_urls():
        if schedule:
            scheduler.add_job(id=url_["Id"],  args=[url_["Id"]], func=check_for_changes, trigger='cron', **cron_to_dict(schedule))
        else:
            scheduler.add_job(id=url_["Id"],  args=[url_["Id"]], func=check_for_changes, trigger='interval', minutes=interval)

    # Run the job once immediately
    # scheduler.add_job(id = id , func=check_for_changes, trigger='date', run_date=datetime.now())
        service.update_url((url_["Id"]), URL=None, status=1)

    flash('Monitoring started!', 'success')
    # Add a small delay to allow the first check to complete
    sleep(2)
    return redirect(url_for('dashboard'))


@app.route("/edit/<string:id>", methods=['GET', 'PUT'])
def edit_url(id):
    # if request.method == 'PUT':
    #     title = request.form.get('title')
    #     content = request.form.get('content')
    #     urls.update_post(id, title=title, content=content)
    #     return show_post(post_id)

    # Default: GET
    url = service.get_url(id)
    return render_template('edit.html', url=url)


@app.route('/stop/<string:id>', methods=['POST'])
def stop_monitoring(id):
    scheduler.remove_job(id)
    service.update_url(id, URL=None, status=0)
    flash('Monitoring stopped!', 'warning')
    return redirect(url_for('index'))

@app.route('/config/<string:id>', methods=['GET', 'POST'])
def config_html(id):
    global html_code
    url = service.get_url(id)
    if request.method == 'POST':
        html_code=request.form['content_url']
        filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url['URL'])}.html"
        report_path = os.path.join('htmlfiles', filename)
        if not os.path.exists('htmlfiles'):
            os.makedirs('htmlfiles')
        with open(report_path, 'w') as f:
            f.write(html_code)
        setup_dynamic(url)
    filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url['URL'])}.html"
    report_path = os.path.join('htmlfiles', filename)
    if not os.path.exists('htmlfiles'):
        os.makedirs('htmlfiles')

    if not os.path.isfile(report_path):
        # Create a report file if it doesn't exist
        flash('File did not exist, start again', 'info')
    else:
        with open(report_path, 'r') as file:
            html_code=file.read()
    return render_template('dynamic.html', content_url=html_code,id=id)


@app.route('/save_config', methods=['POST'])
def save_config():
    global html_code
    id=request.form['id']
    url = service.get_url(id)
    if request.method == 'POST':
        html_code=request.form['content_url']
        filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url['URL'])}.html"
        report_path = os.path.join('htmlfiles', filename)
        if not os.path.exists('htmlfiles'):
            os.makedirs('htmlfiles')
        with open(report_path, 'w') as f:
            f.write(html_code)
    setup_dynamic(url)

    return redirect(url_for('edit_url',id=url["Id"]))




@app.route('/save/<string:id>')
def save(id):
    url = service.get_url(id)
    url_literal=url["URL"]
    filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url_literal)}.html"
    report_path = os.path.join('htmlfiles', filename)

    if not os.path.exists('htmlfiles'):
        os.makedirs('htmlfiles')

    with open(report_path, 'w') as f:
        new_content = get_page_content(url_literal)
        soup = BeautifulSoup(new_content, 'html5lib')
        new_content = str(soup.find('body'))
        f.write(new_content)
    return redirect(url_for('edit_url',id=url["Id"]))



@app.route('/dashboard')
def dashboard():
    global  last_checks
    urls=service.get_urls()
    load_last_checks()  # Load the latest last_checks data
    # print(last_checks)
    return render_template('dashboard.html', urls=urls, last_checks=last_checks)

@app.route('/download_report/<path:url>')
def download_report(url):
    filename = f"report_{re.sub('[^a-zA-Z0-9_]', '_', url)}.txt"
    report_path = os.path.join('reports', filename)
    
    if not os.path.exists('reports'):
        os.makedirs('reports')
    
    if not os.path.isfile(report_path):
        # Create a report file if it doesn't exist
        with open(report_path, 'w') as f:
            f.write(f"No checks have been performed yet for {url}\n")
            f.write(f"Last known check time: {last_checks.get(url, 'Never')}\n")
            f.write(f"Current monitoring status: {'Active' if scheduler.get_job('MonitorJob') else 'Inactive'}\n")
    
    return send_file(report_path, as_attachment=True)

@app.route('/clearsave/<string:id>')
def clear(id):
    global urls, last_checks, previous_domtree, previous_hashes, previous_contents, previous_screenshots
    URL=service.get_url(id)
    for ind in range(len(urls)):
        if ind not in range(len(urls)):
            break
        if urls[ind]==URL["URL"]:
            urls.pop(ind)
    if URL["URL"] in last_checks:
        del last_checks[URL]
    if URL["URL"] in previous_domtree:
        del previous_domtree[URL]
    if URL["URL"] in previous_hashes:
        del previous_hashes[URL]
    if URL["URL"] in previous_contents:
        del previous_contents[URL]
    if URL["URL"] in previous_screenshots:
        del previous_screenshots[URL]
    service.clear_url(id)
    return redirect(url_for('dashboard'))


@app.route('/clear_list')
def clear_list():
    global urls, last_checks
    urls = []
    service.clear_urls()
    last_checks = {}
    flash('Monitored URLs and reports have been cleared.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/screenshot/<string:id>')
def get_screenshot(id):
    url=service.get_url(id)
    filename = f"{re.sub('[^a-zA-Z0-9_]', '_', url['URL'])}.png"
    return send_from_directory('screenshots', filename)

def cron_to_dict(cron_string):
    minute, hour, day, month, day_of_week = cron_string.split()
    return {
        'minute': minute,
        'hour': hour,
        'day': day,
        'month': month,
        'day_of_week': day_of_week
    }

if __name__ == '__main__':
    load_config()
    load_last_checks()
    load_log()
    scheduler.add_job(id='LOGDUMP',func=log_dump, trigger='interval', minutes=10)
    if not os.path.exists('reports'):
        os.makedirs('reports')
    if not os.path.exists('screenshots'):
        os.makedirs('screenshots')
    if not os.path.exists('htmlfiles'):
        os.makedirs('htmlfiles')
    app.run(debug=True)
