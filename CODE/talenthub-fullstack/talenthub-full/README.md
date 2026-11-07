# TalentHub (Flask + SQLite)
    pip install -r requirements.txt
    python app.py        # open http://127.0.0.1:5000
One login page for everyone; the site detects whether the account is a student or a recruiter.
Student:  student@demo.com / Student@123
Recruiters: infosys@talenthub.com / Infy#Hire26 ; wipro@talenthub.com / Wipro#Hire26 ; bosch@talenthub.com / Bosch#Hire26 ; thoughtworks@talenthub.com / Tw#Hire26
Delete talenthub.db and restart if you ran an older version. Change the seed passwords in app.py and set SECRET_KEY before real use.
