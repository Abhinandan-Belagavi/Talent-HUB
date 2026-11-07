import os, sqlite3
from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash as gen, check_password_hash as chk
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'talenthub.db')
app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
BRANCHES = {'CSE', 'ECE', 'EEE', 'ME'}
RECRUITER_PW = {'Infosys': 'Infy#Hire26', 'Wipro': 'Wipro#Hire26', 'Bosch': 'Bosch#Hire26', 'Thoughtworks': 'Tw#Hire26'}

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db
@app.teardown_appcontext
def close(_):
    d = g.pop('db', None)
    if d: d.close()
def q(sql, a=(), one=False):
    r = [dict(x) for x in db().execute(sql, a).fetchall()]
    return (r[0] if r else None) if one else r
def run(sql, a=()):
    c = db().execute(sql, a); db().commit(); return c.lastrowid
def err(m, c=400): return jsonify(error=m), c
def need(role): return session.get('role') == role

def init_db():
    d = sqlite3.connect(DB); d.executescript(open(os.path.join(BASE, 'schema.sql')).read())
    if not d.execute('SELECT 1 FROM companies').fetchone():
        pw = gen('Student@123')
        d.execute("INSERT INTO students(usn,name,email,password_hash,branch,cgpa,backlogs) VALUES('2KA22CS014','Ananya Kulkarni','student@demo.com',?,'CSE',8.4,0)", (pw,))
        jobs = [('Infosys','Systems Engineer',6.5,6.5,0,'CSE,ECE,EEE'),('Wipro','Project Engineer',4.5,6,1,'CSE,ECE,EEE,ME'),
                ('Bosch','Embedded Developer',9,8,0,'ECE,EEE'),('Thoughtworks','Software Developer',12,8.5,0,'CSE')]
        for n, r, p, c, b, br in jobs:
            cid = d.execute('INSERT INTO companies(name,email,password_hash) VALUES(?,?,?)', (n, n.lower() + '@talenthub.com', gen(RECRUITER_PW[n]))).lastrowid
            jid = d.execute("INSERT INTO job_listings(company_id,role,package_lpa,min_cgpa,max_backlogs,deadline) VALUES(?,?,?,?,?,'2026-12-31')", (cid, r, p, c, b)).lastrowid
            d.executemany('INSERT INTO job_allowed_branches VALUES(?,?)', [(jid, x) for x in br.split(',')])
    d.commit(); d.close()

@app.route('/')
def home(): return send_from_directory('static', 'index.html')

@app.get('/api/me')
def me():
    if not session.get('role'): return jsonify(role=None)
    return jsonify(role=session['role'], name=session['name'])

@app.post('/api/register')
def register():
    d = request.get_json(force=True)
    try:
        cg, bk = float(d['cgpa']), int(d['backlogs'])
        if not (0 <= cg <= 10) or bk < 0 or d['branch'] not in BRANCHES or len(d['password']) < 6: raise ValueError
        if q('SELECT 1 x FROM companies WHERE email=?', (d['email'].strip().lower(),), one=True): return err('That email is already registered.', 409)
        sid = run('INSERT INTO students(usn,name,email,password_hash,branch,cgpa,backlogs) VALUES(?,?,?,?,?,?,?)',
                  (d['usn'].strip().upper(), d['name'].strip(), d['email'].strip().lower(), gen(d['password']), d['branch'], cg, bk))
    except sqlite3.IntegrityError: return err('That USN or email is already registered.', 409)
    except (KeyError, ValueError, TypeError): return err('Check the form: password needs 6+ characters, CGPA 0-10.')
    session.update(role='student', uid=sid, name=d['name'].strip()); return jsonify(ok=True)

@app.post('/api/login')
def login():
    d = request.get_json(force=True)
    email, pw = str(d.get('email', '')).strip().lower(), d.get('password', '')
    for role, t, k in (('student', 'students', 'student_id'), ('recruiter', 'companies', 'company_id')):
        u = q(f'SELECT * FROM {t} WHERE email=?', (email,), one=True)
        if u and chk(u['password_hash'], pw):
            session.clear(); session.update(role=role, uid=u[k], name=u['name'])
            return jsonify(ok=True, role=role)
    return err('Wrong email or password.', 401)

@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

def reasons(j, s):
    r = []
    if s['cgpa'] < j['min_cgpa']: r.append(f"CGPA below {j['min_cgpa']}")
    if s['backlogs'] > j['max_backlogs']: r.append(f"Backlogs above {j['max_backlogs']}")
    if s['branch'] not in j['branches']: r.append(f"{s['branch']} branch not allowed")
    return r
def jobs_with_branches(where='', a=()):
    js = q(f'SELECT j.*,c.name company FROM job_listings j JOIN companies c USING(company_id) {where} ORDER BY j.job_id DESC', a)
    for j in js: j['branches'] = [x['branch'] for x in q('SELECT branch FROM job_allowed_branches WHERE job_id=?', (j['job_id'],))]
    return js
def me_student(): return q('SELECT * FROM students WHERE student_id=?', (session['uid'],), one=True)

# ---------- student ----------
@app.get('/api/student')
def student():
    if not need('student'): return err('Login required', 401)
    s = me_student(); s.pop('password_hash'); return jsonify(s)

@app.get('/api/jobs')
def jobs():
    if not need('student'): return err('Login required', 401)
    s = me_student()
    done = {x['job_id'] for x in q('SELECT job_id FROM applications WHERE student_id=?', (s['student_id'],))}
    js = jobs_with_branches()
    for j in js: j['reasons'] = reasons(j, s); j['applied'] = j['job_id'] in done
    return jsonify(js)

@app.post('/api/apply')
def apply():
    if not need('student'): return err('Login required', 401)
    s = me_student()
    js = jobs_with_branches('WHERE j.job_id=?', (request.get_json(force=True).get('job_id'),))
    if not js: return err('Job not found', 404)
    if reasons(js[0], s): return err('You are not eligible for this job.', 403)
    try: run('INSERT INTO applications(student_id,job_id) VALUES(?,?)', (s['student_id'], js[0]['job_id']))
    except sqlite3.IntegrityError: return err('You already applied.', 409)
    return jsonify(ok=True)

@app.get('/api/applications')
def my_apps():
    if not need('student'): return err('Login required', 401)
    return jsonify(q('SELECT a.application_id,a.status,a.applied_on,c.name company,j.role FROM applications a JOIN job_listings j USING(job_id) JOIN companies c USING(company_id) WHERE a.student_id=? ORDER BY a.application_id DESC', (session['uid'],)))

@app.get('/api/interviews')
def my_interviews():
    if not need('student'): return err('Login required', 401)
    return jsonify(q('SELECT i.*,c.name company FROM interview_slots i JOIN applications a USING(application_id) JOIN job_listings j USING(job_id) JOIN companies c USING(company_id) WHERE a.student_id=? ORDER BY i.scheduled_at', (session['uid'],)))

@app.get('/api/offers')
def my_offers():
    if not need('student'): return err('Login required', 401)
    return jsonify(q('SELECT o.*,c.name company,j.role FROM offers o JOIN applications a USING(application_id) JOIN job_listings j USING(job_id) JOIN companies c USING(company_id) WHERE a.student_id=?', (session['uid'],)))

@app.post('/api/offers/<int:oid>/respond')
def respond(oid):
    if not need('student'): return err('Login required', 401)
    st = request.get_json(force=True).get('status')
    o = q('SELECT o.offer_id,o.status FROM offers o JOIN applications a USING(application_id) WHERE o.offer_id=? AND a.student_id=?', (oid, session['uid']), one=True)
    if not o or st not in ('Accepted', 'Declined') or o['status'] != 'Pending': return err('Cannot update this offer.')
    run('UPDATE offers SET status=? WHERE offer_id=?', (st, oid)); return jsonify(ok=True)

# ---------- recruiter ----------
def own_app(aid):
    return q('SELECT a.application_id FROM applications a JOIN job_listings j USING(job_id) WHERE a.application_id=? AND j.company_id=?', (aid, session.get('uid')), one=True)

@app.get('/api/recruiter/summary')
def summary():
    if not need('recruiter'): return err('Login required', 401)
    f = lambda sql: q(sql, (session['uid'],), one=True)['n']
    J = 'JOIN job_listings j USING(job_id) WHERE j.company_id=?'
    return jsonify(jobs=f('SELECT COUNT(*) n FROM job_listings WHERE company_id=?'),
        applicants=f(f'SELECT COUNT(*) n FROM applications a {J}'),
        shortlisted=f(f"SELECT COUNT(*) n FROM applications a {J} AND a.status='Shortlisted'"),
        offers=f(f'SELECT COUNT(*) n FROM offers o JOIN applications a USING(application_id) {J}'))

@app.route('/api/recruiter/jobs', methods=['GET', 'POST'])
def rjobs():
    if not need('recruiter'): return err('Login required', 401)
    if request.method == 'GET': return jsonify(jobs_with_branches('WHERE j.company_id=?', (session['uid'],)))
    d = request.get_json(force=True)
    try:
        br = [b for b in d['branches'] if b in BRANCHES]
        if not br or not d['role'].strip(): raise ValueError
        jid = run('INSERT INTO job_listings(company_id,role,package_lpa,min_cgpa,max_backlogs,deadline) VALUES(?,?,?,?,?,?)',
                  (session['uid'], d['role'].strip(), float(d['package_lpa']), float(d['min_cgpa']), int(d.get('max_backlogs') or 0), d.get('deadline') or None))
        db().executemany('INSERT INTO job_allowed_branches VALUES(?,?)', [(jid, b) for b in br]); db().commit()
    except (KeyError, ValueError, TypeError): return err('Fill role, package, CGPA and pick at least one branch.')
    return jsonify(ok=True)

@app.get('/api/recruiter/applicants')
def applicants():
    if not need('recruiter'): return err('Login required', 401)
    return jsonify(q('SELECT a.application_id,a.status,s.name,s.usn,s.branch,s.cgpa,s.backlogs,j.role,j.package_lpa,(SELECT COUNT(*) FROM offers o WHERE o.application_id=a.application_id) has_offer FROM applications a JOIN students s USING(student_id) JOIN job_listings j USING(job_id) WHERE j.company_id=? ORDER BY a.application_id DESC', (session['uid'],)))

@app.post('/api/recruiter/applications/<int:aid>/<action>')
def act(aid, action):
    if not need('recruiter'): return err('Login required', 401)
    if not own_app(aid): return err('Not your applicant.', 403)
    d = request.get_json(force=True)
    if action == 'status':
        if d.get('status') not in ('Applied', 'Shortlisted', 'Interview scheduled', 'Offered', 'Rejected'): return err('Bad status')
        run('UPDATE applications SET status=? WHERE application_id=?', (d['status'], aid))
    elif action == 'interview':
        if not (d.get('round') and d.get('scheduled_at') and d.get('venue')): return err('Round, date and venue are required.')
        run('INSERT INTO interview_slots(application_id,round,scheduled_at,venue) VALUES(?,?,?,?)', (aid, d['round'], d['scheduled_at'], d['venue']))
        run("UPDATE applications SET status='Interview scheduled' WHERE application_id=?", (aid,))
    elif action == 'offer':
        try: run('INSERT INTO offers(application_id,package_lpa) VALUES(?,?)', (aid, float(d['package_lpa'])))
        except (sqlite3.IntegrityError, KeyError, ValueError): return err('Offer already exists or package is invalid.')
        run("UPDATE applications SET status='Offered' WHERE application_id=?", (aid,))
    else: return err('Unknown action', 404)
    return jsonify(ok=True)

init_db()
if __name__ == '__main__':
    app.run(debug=True, port=5000)
