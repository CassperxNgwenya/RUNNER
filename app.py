from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import json
import os
import uuid
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# ============================================
# FILE PATHS (All local JSON files)
# ============================================
JOBS_FILE = 'jobs.json'
LEDGER_FILE = 'ledger.json'
USERS_FILE = 'users.json'

# ============================================
# HELPER FUNCTIONS
# ============================================

def load_json(filename):
    """Load JSON file safely."""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return []

def save_json(filename, data):
    """Save JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def init_files():
    """Initialize empty JSON files if they don't exist."""
    if not os.path.exists(JOBS_FILE):
        save_json(JOBS_FILE, [])
    if not os.path.exists(LEDGER_FILE):
        save_json(LEDGER_FILE, [])
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, [
            {'username': 'admin', 'password': 'admin123', 'role': 'admin'},
            {'username': 'dispatcher', 'password': 'disp123', 'role': 'dispatcher'}
        ])

def login_required(f):
    """Decorator to require login for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user') or session.get('role') != 'admin':
            flash('Access denied. Admin only.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# ROUTES: AUTHENTICATION
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Simple password-based login."""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        users = load_json(USERS_FILE)
        for user in users:
            if user['username'] == username and user['password'] == password:
                session['user'] = username
                session['role'] = user['role']
                return redirect(url_for('dashboard'))
        
        flash('Invalid username or password.')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Log out user."""
    session.clear()
    return redirect(url_for('login'))

# ============================================
# ROUTES: CUSTOMER (Public)
# ============================================

@app.route('/')
def index():
    """Home page / landing."""
    return render_template('index.html')

@app.route('/request', methods=['GET', 'POST'])
def customer_request():
    """Customer submits an errand request."""
    if request.method == 'POST':
        # Collect form data
        customer_name = request.form.get('customer_name', '')
        phone = request.form.get('phone', '')
        location = request.form.get('location', '')
        errand_details = request.form.get('errand_details', '')
        payment_method = request.form.get('payment_method', '')
        
        # Validate
        if not all([customer_name, phone, location, errand_details, payment_method]):
            flash('All fields are required.')
            return render_template('customer_request.html')
        
        # Generate job ID
        job_id = str(uuid.uuid4())[:8].upper()
        
        # Create job object
        job = {
            'job_id': job_id,
            'customer_name': customer_name,
            'phone': phone,
            'location': location,
            'errand_details': errand_details,
            'payment_method': payment_method,
            'status': 'New',
            'price': '',
            'runner': '',
            'paid': False,
            'completed': False,
            'created_date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        # Save job
        jobs = load_json(JOBS_FILE)
        jobs.append(job)
        save_json(JOBS_FILE, jobs)
        
        return render_template('thank_you.html', job_id=job_id)
    
    return render_template('customer_request.html')

@app.route('/status', methods=['GET', 'POST'])
def job_status():
    """Customer checks job status by Job ID."""
    job = None
    if request.method == 'POST':
        job_id = request.form.get('job_id', '').upper()
        jobs = load_json(JOBS_FILE)
        for j in jobs:
            if j['job_id'] == job_id:
                job = j
                break
        if not job:
            flash('Job ID not found.')
    
    return render_template('job_status.html', job=job)

@app.route('/receipt/<job_id>')
def receipt(job_id):
    """View digital receipt for a completed job."""
    job_id = job_id.upper()
    jobs = load_json(JOBS_FILE)
    
    for job in jobs:
        if job['job_id'] == job_id:
            # Only show receipt if job is completed
            if not job.get('completed', False):
                return render_template('error.html', 
                    message='Receipt not available yet. Job has not been completed.'), 404
            return render_template('receipt.html', job=job)
    
    return render_template('error.html', message='Job not found.'), 404

# ============================================
# ROUTES: ADMIN / DISPATCHER DASHBOARD
# ============================================

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    """Main admin/dispatcher dashboard."""
    jobs = load_json(JOBS_FILE)
    
    if request.method == 'POST':
        job_id = request.form.get('job_id', '')
        action = request.form.get('action', '')
        
        # Find job
        for job in jobs:
            if job['job_id'] == job_id:
                # ASSIGN RUNNER
                if action == 'assign_runner':
                    runner = request.form.get('runner', '')
                    if runner:
                        job['runner'] = runner
                        job['status'] = 'Assigned'
                        flash(f'Runner {runner} assigned to job {job_id}.')
                
                # SET PRICE
                elif action == 'set_price':
                    price = request.form.get('price', '')
                    if price and price.replace('.', '', 1).isdigit():
                        job['price'] = float(price)
                        flash(f'Price R{price} set for job {job_id}.')
                    else:
                        flash('Invalid price.')
                
                # CONFIRM PAYMENT
                elif action == 'confirm_payment':
                    if not job.get('price'):
                        flash('Cannot confirm payment: price not set.')
                    else:
                        job['paid'] = True
                        job['status'] = 'Confirmed Paid'
                        flash(f'Payment confirmed for job {job_id}.')
                
                # MARK COMPLETED
                elif action == 'mark_completed':
                    if not job.get('paid'):
                        flash('Cannot complete: payment not confirmed.')
                    else:
                        job['completed'] = True
                        job['status'] = 'Completed'
                        job['completed_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                        
                        # Add to ledger
                        ledger = load_json(LEDGER_FILE)
                        entry = {
                            'job_id': job['job_id'],
                            'customer_name': job['customer_name'],
                            'amount': job.get('price', 0),
                            'payment_method': job['payment_method'],
                            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
                        }
                        ledger.append(entry)
                        save_json(LEDGER_FILE, ledger)
                        
                        flash(f'Job {job_id} marked completed and added to ledger.')
                
                save_json(JOBS_FILE, jobs)
                break
    
    return render_template('dashboard.html', jobs=jobs)

# ============================================
# ROUTES: LEDGER / BOOKKEEPING
# ============================================

@app.route('/ledger')
@login_required
def ledger():
    """View ledger of completed/paid jobs."""
    ledger_data = load_json(LEDGER_FILE)
    total = sum(float(entry.get('amount', 0)) for entry in ledger_data)
    return render_template('ledger.html', ledger=ledger_data, total=total)

# ============================================
# ROUTES: LEGAL PAGES
# ============================================

@app.route('/terms')
def legal_terms():
    """Terms & Conditions."""
    return render_template('legal_terms.html')

@app.route('/privacy')
def legal_privacy():
    """Privacy Policy."""
    return render_template('legal_privacy.html')

@app.route('/refund')
def legal_refund():
    """Refund Policy."""
    return render_template('legal_refund.html')

# ============================================
# ERROR HANDLING
# ============================================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message='Page not found.'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', message='Server error.'), 500

# ============================================
# STARTUP
# ============================================

if __name__ == '__main__':
    init_files()
    app.run(debug=True, host='0.0.0.0', port=5000)