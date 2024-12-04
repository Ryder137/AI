from flask import Flask, request, jsonify, render_template, session, send_from_directory, url_for
import google.generativeai as genai
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import uuid
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import pytz  # Import pytz for timezone handling
import re
import logging
import requests
import calendar 
from collections import Counter
from dotenv import load_dotenv
import pymysql
from waitress import serve

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
app.secret_key = 'beibotna' 
socketio = SocketIO(app)
bot_information = []
pymysql.install_as_MySQLdb()
load_dotenv()


# Configure the database connection
DB_USER = 'root'
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = 'localhost'
DB_NAME = 'students_db'
# Update this line in your code
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'

# SQLAlchemy setup
Base = declarative_base(name="Base")
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
Session = sessionmaker(bind=engine)
db_session = scoped_session(Session)

# Define the Student model
class Student(Base):
    __tablename__ = 'students'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    student_id = Column(String(9), unique=True)  # Assuming 9-digit ID
    email = Column(String(100), nullable=True)

class Conversation(Base):
    __tablename__ = 'conversations'
    
    conversation_id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True)
    student_id = Column(String(9))
    email = Column(String)
    timestamp = Column(DateTime, default=datetime.now(pytz.timezone('Asia/Manila')))  # Set default to Philippine time

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __init__(self, session_id, student_id, email, timestamp=None):
        self.session_id = session_id
        self.student_id = student_id
        self.email = email
        self.timestamp = timestamp or datetime.now(pytz.timezone('Asia/Manila'))  # Set timestamp if provided

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(9), ForeignKey('students.student_id'))
    email = Column(String(255), nullable=True)
    query = Column(String(255))
    response = Column(String(999))
    timestamp = Column(DateTime, default=datetime.now(pytz.timezone('Asia/Manila')))  # Set default to Philippine time
    session_id = Column(String, ForeignKey('conversations.session_id'))

    conversation = relationship("Conversation", back_populates="messages")

    def __init__(self, student_id, query, response, email, session_id, timestamp=None):
        self.student_id = student_id
        self.query = query
        self.response = response
        self.email = email
        self.session_id = session_id
        self.timestamp = timestamp or datetime.now(pytz.timezone('Asia/Manila'))  # Corrected line

Base.metadata.create_all(engine)

# Configure API key for Google Generative AI
api_key = os.getenv("GEMINI_API_KEY")

# Debugging output
print(f"API Key found: {'Yes' if api_key else 'No'}")  # Check if API key is present

if not api_key:
    raise ValueError("No API key found. Set the GEMINI_API_KEY environment variable.")

# Configure the Google Generative AI
genai.configure(api_key=api_key)
print("Google Generative AI configured successfully.")

# Model definition
generation_config = {
    "temperature": 0.15,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction="""You are Biebot the AI assistant for the College of Computer Studies. You will be answering student queries related to the department, always in a formal but joyful tone to be more friendly to students  you can use emojis to me more friendly to students..
    Provide the following information for specific queries:
    1. Enrollment: 
        - answer here based on the question about enrollment. 
        For New Students (Freshmen):
        - Application Form – Completed and signed the form from the Admission Office.
        - High School Report Card (Form 138) – Final grades from senior high school.
        - Certificate of Good Moral Character – Issued by the high school.
        - Photocopy of Birth Certificate – From the Philippine Statistics Authority (PSA)
        - 2x2 or 1x1 ID Photos – As specified by the school.
        - Entrance Examination Results – Passing the university’s entrance exam.
        - Medical Clearance/Health Certificate – Medical exam results may be required. Can be done at the University Clinic.
        - Copy of High School Diploma.

    For Transferees:
        - Honorable Dismissal/Transfer Credentials – From the previous school.
        - Transcript of Records – Reflecting grades from previous semesters.
        - Certificate of Good Moral Character – From the previous institution.
        - 2x2 or 1x1 ID Photos.
        - Photocopy of Birth Certificate (PSA).
        - Entrance Examination Results (if applicable).

    For Returning Students:
        - Clearance – From the last semester attended.
        - Evaluation Form – Issued by the Registrar’s Office.
        - 2x2 or 1x1 ID Photos.
    2. Adding/Dropping Subjects: 
        - Answer this on a step procedure:
            "Visit the Registrar's office. 
            Fill out the application form and list the subjects you wish to modify. 
            Submit to the Dean's Office to get the signature from the Dean. 
            Go back to the Registrar's office to process it."
    3. Tuition Fees:
        - "Tuition fees are based on the number of units. You can email our Cashier Office: molacctg@perpetualdalta.edu.ph or you may visit our Cashier Office 8:00am - 5:00pm"
    4. Contact of the Professors: 
        - Here are the emails of the Professors:
        Prof. Maribel Sandagon - maribel.sandagon@perpetualdalta.edu.ph
        Prof. Fe M. Antonio - fe.antonio@perpetualdalta.edu.ph
        Prof. Dolores L. Montesines - dmontesines125@gmail.com
        ENGR. Val Patrick Fabregas - valpatrick.fabregas@perpetual.edu.ph
        ENGR. Jonel Macalisang - jonelmacalisang@gmail.com
        Prof. Arnold B. Galve - abgalve@gmail.com
        DR. Luvim Eusebio - luvim.eusebio@perpetualdalta.edu.ph
        ENGR. Ailyn Manero - ailyn.manero@perpetual.edu.ph
        DR. Mark Anthony Cezar - markanthony.cezar@perpetual.edu.ph
        Prof. Edward N. Cruz - encruz.1116@gmail.com
        ENGR. Roberto L. Malitao - robertomalitao@gmail.com 
    5. Course Offerings: 
        - "You can view the list of course offerings for the next semester on the student portal. If you need assistance choosing courses, the registrar or your department advisor can help."
    6. Exam Schedules: 
        - "The exam schedules will be announced by your Professors."
    7. Dean`s Lister/ Scholarship:
        - Answer this in a step by step form and bulleted form.
        "Obtain an Application Form:
                Visit the Office of the Dean or your department’s Student Affairs Office to request a Dean’s List application form or check if the application process is automated.
                Some universities handle the Dean’s List process automatically, where students are notified if they qualify. However, others may require you to apply.
        Submit Necessary Documents:
                Completed Application Form: Fill out and sign the form.
                Grades or Transcript of Records: A copy of your grades or evaluation form for the semester in which you qualify.
        Check for Conduct :
                You should have a clean disciplinary record—no major violations of the university’s rules.
                Sign of the Prefect of Discipline Of the University 
        Submit the Application:
                Submit your application to the Dean’s Office or designated office before the deadline.
        Wait for Approval:
                The Dean and other university officials will review your application, verify your academic standing, and approve qualified students.
                The College of Computer Studies office RM 200 is open from 8:00 AM to 5:00 PM, Monday to Wednesday. For specific concerns, feel free to visit during office hours."
    9. General inquiries :
        - "For general inquiries, you can email us at ccs.molino@perpetualdalta.edu.ph or visit our office 2nd Floor, Room 200. 
        The enrollment process, including adding or dropping classes, is handled at Room 203 during the enrollment period, with class drops requiring an adding/dropping form from the registrar. Document requests, such as transcripts or certificates, can be made at the registrar’s office, 
        typically taking 3-5 working days to process. Tuition and other fees are payable only at the school cashier, with a breakdown of fees available upon request. For more detailed information."
        
     10. Faculty:
        - Answer this in a bullet form and bold the words: Dean, Secretary and Professors 
        Dean: 
        Prof. Maribel Sandagon 
        Secretary: 
        Ms. Febie M. Portilla
        Professors
        Prof. Fe M. Antonio
        Prof. Dolores L. Montesines
        ENGR. Val Patrick Fabregas
        ENGR. Jonel Macalisang 
        Prof. Arnold B. Galve
        DR. Luvim Eusebio
        ENGR. Ailyn Manero
        DR. Mark Anthony Cezar
        Prof. Edward N. Cruz
        ENGR. Roberto L. Malitao
    11.Student portal and fb page:
    - Click the perpetual logo for the student portal and the ccs logo for the fb page
    12. Classes today, tomorrow:
        "Check the facebook page https://www.facebook.com/perpetualmolino, or the local news https://news.abs-cbn.com. if there is any cancelation"
        """,
)

# Model definition with responses in Tagalog
generation_config = {
    "temperature": 0.15,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction="""Ikaw ay si Biebot, ang AI assistant para sa Kolehiyo ng Computer Studies. Sasagutin mo ang mga katanungan ng mga estudyante na may kaugnayan sa departamento, palaging sa pormal ngunit masayang tono, Pwede mong gamitin ang mga emoji para maging mas magiliw sa mga estudyante. .
    Magbigay ng mga kaugnay na impormasyon para sa mga katanungan tulad ng: 
    1. Pagpapa-enrol:
        - sagot dito batay sa tanong tungkol sa pagpapa-enrol.
        Para sa mga Bagong Estudyante (Freshmen):
        - Form ng Aplikasyon – Kumpletuhin at pirmahan ang form mula sa Tanggapan ng Pagtanggap.
        - Report Card ng Mataas na Paaralan (Form 138) – Huling mga grado mula sa senior high school.
        - Sertipiko ng Mabuting Moral na Katangian – Ipinagkaloob ng mataas na paaralan.
        - Photocopy ng Sertipiko ng Kapanganakan – Mula sa Philippine Statistics Authority (PSA).
        - 2x2 o 1x1 ID Photos – Ayon sa itinakdang mga kinakailangan ng paaralan.
        - Mga Resulta ng Entrance Examination – Nakatanggap ng marka na pumasa sa entrance exam ng unibersidad.
        - Medical Clearance/Health Certificate – Maaaring kailanganin ang mga resulta ng medikal na pagsusuri. Maaaring isagawa sa Unibersidad na Klinika.
        - Kopya ng Diploma sa Mataas na Paaralan.

    Para sa mga Transferees:
        - Honorable Dismissal/Transfer Credentials – Mula sa nakaraang paaralan.
        - Transcript of Records – Na nagpapakita ng mga grado mula sa nakaraang mga semester.
        - Sertipiko ng Mabuting Moral na Katangian – Mula sa nakaraang institusyon.
        - 2x2 o 1x1 ID Photos.
        - Photocopy ng Sertipiko ng Kapanganakan (PSA).
        - Mga Resulta ng Entrance Examination (kung kinakailangan).

    Para sa mga Nagbabalik na Estudyante:
        - Clearance – Mula sa huling semester na tinapos.
        - Evaluation Form – Ipinagkaloob ng Tanggapan ng Tagatala.
        - 2x2 o 1x1 ID Photos.
    2. Pagdagdag/Pagtanggal ng mga Paksa: 
        - Sagutin ito sa hakbang na pamamaraan:
            "Bisitahin ang tanggapan ng Tagatala. Kumpletuhin ang form ng aplikasyon at ilista ang mga paksa na nais mong baguhin. Isumite ito sa Tanggapan ng Dekano upang makuha ang pirma mula sa Dekano. Balik sa tanggapan ng Tagatala upang iproseso ito."
    3. Bayad sa Tuition:
        - "Ang mga bayad sa tuition ay batay sa bilang ng mga yunit. Maaari mong i-email ang aming Tanggapan ng Cashier: molacctg@perpetualdalta.edu.ph o maaari mong bisitahin ang aming Tanggapan ng Cashier mula 8:00 ng umaga hanggang 5:00 ng hapon."
    4. Makipag-ugnayan sa mga Propesor: 
        - Narito ang mga email ng mga Propesor:
        Prof. Maribel Sandagon - maribel.sandagon@perpetualdalta.edu.ph
        Prof. Fe M. Antonio - fe.antonio@perpetualdalta.edu.ph
        Prof. Dolores L. Montesines - dmontesines125@gmail.com
        ENGR. Val Patrick Fabregas - valpatrick.fabregas@perpetual.edu.ph
        ENGR. Jonel Macalisang - jonelmacalisang@gmail.com
        Prof. Arnold B. Galve - abgalve@gmail.com
        DR. Luvim Eusebio - luvim.eusebio@perpetualdalta.edu.ph
        ENGR. Ailyn Manero - ailyn.manero@perpetual.edu.ph
        DR. Mark Anthony Cezar - markanthony.cezar@perpetual.edu.ph
        Prof. Edward N. Cruz - encruz.1116@gmail.com
        ENGR. Roberto L. Malitao - robertomalitao@gmail.com 
    5. Mga Kurso: 
        - "Maaari mong tingnan ang listahan ng mga kurso para sa susunod na semester sa student portal. Kung kailangan mo ng tulong sa pagpili ng mga kurso, ang tagatala o iyong tagapayo ng departamento ay makakatulong."
    6. Iskedyul ng Pagsusulit: 
        - "Ang iskedyul ng pagsusulit ay iaanunsyo ng iyong mga Propesor."
    7. Dean's Lister/Siyensya: 
        - Sagutin ito sa hakbang-hakbang na anyo at may mga bullet point.
        "Kumuha ng Form ng Aplikasyon:
                Bisitahin ang Tanggapan ng Dekano o ng Student Affairs Office ng iyong departamento upang humiling ng form ng aplikasyon para sa Dean's List o suriin kung ang proseso ng aplikasyon ay automated.
                Ang ilang unibersidad ay awtomatikong pinangangasiwaan ang proseso ng Dean’s List, kung saan ang mga estudyante ay pinapaalam kung sila ay kwalipikado. Gayunpaman, ang iba ay maaaring kailanganin mong mag-aplay.
        Isumite ang Mga Kinakailangang Dokumento:
                Nakumpletong Form ng Aplikasyon: Punan at pirmahan ang form.
                Mga Grado o Transcript of Records: Kopya ng iyong mga grado o evaluation form para sa semester kung saan ka kwalipikado.
        Suriin ang Pag-uugali:
                Dapat ay mayroon kang malinis na rekord sa disiplina—walang malalaking paglabag sa mga alituntunin ng unibersidad.
                Pirma ng Prefect of Discipline ng Unibersidad.
        Isumite ang Aplikasyon:
                Isumite ang iyong aplikasyon sa Tanggapan ng Dekano o itinakdang opisina bago ang takdang panahon.
        Maghintay ng Pag-apruba:
                Suriin ng Dekano at iba pang mga opisyal ng unibersidad ang iyong aplikasyon, i-verify ang iyong katayuan sa akademiko, at aprubahan ang mga kwalipikadong estudyante.
                Ang opisina ng Kolehiyo ng Computer Studies ay bukas mula 8:00 AM hanggang 5:00 PM, Lunes hanggang Miyerkules. Para sa mga tiyak na alalahanin, huwag mag-atubiling bumisita sa oras ng opisina."
    9. Mga Pangkalahatang Katanungan:
        - Para sa mga pangkalahatang katanungan, maaari kayong mag-email sa ccs.molino@perpetualdalta.edu.ph o bumisita sa aming opisina sa 2nd Floor, Room 200.
Kung may tanong tungkol sa petsa o oras, sasagutin namin ito, at aming sisiguraduhing walang holiday sa nasabing petsa.
Ang proseso ng enrollment, kabilang ang pagdagdag o pagbawas ng klase, ay isinasagawa sa Room 203 sa panahon ng enrollment. Ang pagbawas ng klase ay nangangailangan ng Adding/Dropping Form mula sa registrar.
Para sa mga kahilingan ng dokumento tulad ng transcript o certificate, pumunta lamang sa tanggapan ng registrar. Karaniwang tumatagal ng 3-5 working days ang pagproseso.
Ang pagbabayad ng matrikula at iba pang bayarin ay ginagawa lamang sa school cashier. Maaari ding humiling ng breakdown ng bayarin kung kinakailangan.
    10. Faculty:
        - Sagutin ito sa bullet form at itaga ang mga salita: **Dean**, **Secretary**, at **Professors** 
       " **Dean**: 
        Prof. Maribel Sandagon 
        **Secretary**: 
        Ms. Febie M. Portilla
        **Professors**
        Prof. Fe M. Antonio
        Prof. Dolores L. Montesines
        ENGR. Val Patrick Fabregas
        ENGR. Jonel Macalisang 
        Prof. Arnold B. Galve
        DR. Luvim Eusebio
        ENGR. Ailyn Manero
        DR. Mark Anthony Cezar
        Prof. Edward N. Cruz
        ENGR. Roberto L. Malitao"
        
        11. Portal ng estudyante at pahina ng Facebook:

I-click ang logo ng Perpetual para sa portal ng estudyante at ang logo ng CCS para sa pahina ng Facebook.
12. Mga klase ngayon, bukas:

"Suriin ang pahina ng Facebook sa https://www.facebook.com/perpetualmolino, o ang lokal na balita sa https://news.abs-cbn.com kung mayroong anumang pagkansela."
        """,
)

chat_session = None  # Global variable to store the chat session

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

@app.route('/start_session', methods=['POST'])
def start_session():
    # Clear existing session data if any
    session.clear()

    data = request.get_json()
    session_id = str(uuid4())  # Generate a new unique session ID
    student_id = data.get('student_id')
    email = data.get('email')
    
    # Create a new conversation
    new_conversation = Conversation(session_id=session_id, student_id=student_id, email=email)
    db_session.add(new_conversation)
    db_session.commit()
    
    # Save session ID in user's session data
    session['session_id'] = session_id
    return jsonify({'session_id': session_id})

@app.route('/')
def home():
    return render_template('index.html')

def update_or_create_student(student_name, student_id, email):
    # Check if both student_id and email are empty
    if not student_id and not email:
        raise ValueError("Either Student ID or Email must be provided.")

    # If student_id is provided, use it for lookup
    if student_id:
        student = db_session.query(Student).filter_by(student_id=student_id).first()
    else:
        # If student_id is not provided, use email for lookup
        student = db_session.query(Student).filter_by(email=email).first()

    if student:
        # Update existing student
        student.name = student_name
        if email:  # Update email only if provided
            student.email = email
        if student_id:  # Update student_id only if provided
            student.student_id = student_id
    else:
        # Create new student
        if not student_id:  # If student_id is not provided, set it to None or a default value
            student_id = None  # or some default value if applicable
        student = Student(name=student_name, student_id=student_id, email=email)
        db_session.add(student)

    db_session.commit()
    return student

logging.basicConfig(level=logging.INFO)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json

    user_message = data.get('message')
    student_name = data.get('student_name')
    student_id = data.get('student_id')
    email = data.get('email')

    # Log incoming message
    logging.info(f"Received message from {student_name} (ID: {student_id}): {user_message}")

    # Check for required fields
    if not user_message or not student_name:
        logging.error('Missing required fields.')
        return jsonify({'error': 'Missing required fields: message and student_name.'}), 400

    # Check if either student_id or email is provided
    if not student_id and not email:
        logging.error('Either student ID or email must be provided.')
        return jsonify({'error': 'Either student ID or email must be provided.'}), 400

    sanitized_user_message = sanitize_message(user_message)

    # Check if the user is asking for the current date and time
    if "what is the date" in sanitized_user_message.lower() or "what is the time" in sanitized_user_message.lower():
        current_time = get_current_time()  # Fetch current time from the API
        if current_time:
            date_response = datetime.fromisoformat(current_time).astimezone(pytz.timezone('Asia/Manila')).strftime("%A, %B %d, %Y")
            time_response = datetime.fromisoformat(current_time).astimezone(pytz.timezone('Asia/Manila')).strftime("%I:%M %p")
            response = f"The current date is {date_response} and the time is {time_response}."
        else:
            response = "I'm sorry, but I couldn't fetch the current date and time."

        # Emit the response back to the user
        socketio.emit('receive_message', {
            'query': sanitized_user_message,
            'response': response,
            'student_name': student_name,
            'timestamp': datetime.now(pytz.timezone('Asia/Manila')).isoformat()
        })

        return jsonify({'response': response, 'session_id': session.get('session_id')}), 200

    # Update or create the student record
    student = update_or_create_student(student_name, student_id, email)

    # Ensure student_id is valid if provided
    if student_id and not student.student_id:
        logging.error('Student ID cannot be None or empty.')
        return jsonify({'error': 'Student ID cannot be None or empty.'}), 400

    # Retrieve the session ID from the Flask session
    chat_session = session.get('session_id')

    # Check for existing conversation
    conversation = db_session.query(Conversation).filter_by(session_id=chat_session).first()

    if conversation is None:
        # If no conversation exists, create a new one
        conversation = Conversation(session_id=chat_session, student_id=student.student_id, email=email)
        db_session.add(conversation)
        db_session.commit()  # Commit the new conversation

    # Create a new message
    new_message = Message(
        student_id=student.student_id,
        email=email,
        query=sanitized_user_message,
        response=None,
        session_id=chat_session  # Use the session_id from the Flask session
    )

    db_session.add(new_message)
    
    try:
        db_session.commit()  # Commit the new message
    except Exception as e:
        logging.error(f"Error committing new message: {e}")
        return jsonify({'error': 'Failed to save message.'}), 500

    # Generate the response using the AI model

    try:
        # Combine user query with bot information for context
        context = " ".join(bot_information)  # Join all information into a single string
        full_query = f"{context} {sanitized_user_message}"  # Combine with user query

        logging.info(f"Full query sent to AI model: {full_query}")  # Log the full query

        response = model.generate_content(full_query)
        sanitized_response = response.content if hasattr(response, 'content') else response.text
        sanitized_response = sanitize_message(sanitized_response)

        # Update the response in the database
        new_message.response = sanitized_response  # Save the bot's response
        db_session.commit()  # Commit the response to the database
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return jsonify({'error': 'Failed to generate response.'}), 500

    logging.info(f"Generated response: {sanitized_response}")

    # Emit the new message and response to all connected clients
    socketio.emit('receive_message', {
        'query': sanitized_user_message,
        'response': sanitized_response,
        'student_name': student_name,
        'timestamp': datetime.now(pytz.timezone('Asia/Manila')).isoformat()
    })

    return jsonify({'response': sanitized_response, 'session_id': chat_session}), 200

def get_current_time():
    try:
        response = requests.get("http://worldtimeapi.org/api/timezone/Asia/Manila")  # Use Philippine timezone API
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        current_time = data['datetime']  # Get the current time in ISO format
        return current_time
    except Exception as e:
        logging.error(f"Error fetching current time: {e}")
        return datetime.now(pytz.timezone('Asia/Manila')).isoformat()  # Return current time in Philippine timezone


def sanitize_message(message):
    sanitized = re.sub(r'\*\*([^*]+)\*\*', r'\1', message)
    sanitized = re.sub(r'\*([^*]+)\*', r'\1', sanitized)
    sanitized = re.sub(r'^[\*\-•]\s+', '', sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', sanitized)
    sanitized = re.sub(r'_', '', sanitized)
    sanitized = sanitized.strip()
    return sanitized

@app.route('/get_conversation/<session_id>', methods=['GET'])
def get_conversation(session_id):
    # Retrieve the conversation for the given session_id
    conversation = db_session.query(Conversation).filter_by(session_id=session_id).first()
    
    if not conversation:
        return jsonify({"error": "Conversation not found."}), 404

    # Prepare the response data with all messages in the conversation
    conversation_data = {
        "session_id": conversation.session_id,
        "student_id": conversation.student_id,
        "email": conversation.email,
        "timestamp": conversation.timestamp.isoformat(),
        "messages": [
            {
                "student_id": message.student_id,
                "email": message.email,
                "query": message.query,
                "response": message.response,
                "timestamp": message.timestamp.isoformat()  # Convert to ISO format for JSON serialization
            }
            for message in conversation.messages  # Use the relationship to get messages
        ]
    }

    return jsonify(conversation_data), 200

# Ensure your SQLAlchemy models are imported


@app.route('/get_conversation_history', methods=['POST'])
def get_conversation_history():
    data = request.json
    student_id = data.get("student_id")
    email = data.get("email")

    # Query the conversation table based on student_id or email
    if student_id:
        conversations = db_session.query(Conversation).filter_by(student_id=student_id).all()
    elif email:
        conversations = db_session.query(Conversation).filter_by(email=email).all()
    else:
        return jsonify({"error": "Student ID or email is required"}), 400

    # Format response
    history = [
        {"session_id": convo.session_id, "timestamp": convo.timestamp.isoformat()}
        for convo in conversations
    ]
    return jsonify({"history": history})

@app.route('/get_conversation_messages', methods=['POST'])
def get_conversation_messages():
    data = request.json
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400

    try:
        # Query the database for messages associated with the session_id
        messages = db_session.query(Message).filter_by(session_id=session_id).order_by(Message.timestamp).all()

        if not messages:
            return jsonify({"messages": []}), 200  # Return an empty list if no messages found

        # Format the messages for the response
        message_data = [
            {
                "student_id": msg.student_id,
                "email": msg.email,
                "query": msg.query,
                "response": msg.response,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in messages
        ]

        # Log the response data
        print("Response data:", message_data)

        return jsonify({"messages": message_data}), 200
    except Exception as e:
        # Log the error for debugging
        print("Error retrieving messages:", str(e))
        return jsonify({"error": "An error occurred while retrieving messages."}), 500
    
@app.route('/admin', methods=['GET'])
def admin_panel():
    return render_template('admin_panel.html')  # Ensure you have an HTML file named admin_panel.html

@app.route('/admin/todays_interactions', methods=['GET'])
def todays_interactions():
    try:
        # Get the current date
        now = datetime.now(pytz.timezone('Asia/Manila'))
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = start_of_day + timedelta(days=1)

        # Query messages for today
        messages = db_session.query(Message).filter(
            Message.timestamp >= start_of_day,
            Message.timestamp < end_of_day
        ).all()

        total_messages_today = len(messages)
        questions = [msg.query for msg in messages]

        # Calculate the most common question
        most_common_question = None
        if questions:
            question_counts = Counter(questions)
            most_common_question, _ = question_counts.most_common(1)[0]  # Get the most common question

        return jsonify({
            'total_messages_today': total_messages_today,
            'questions': questions,
            'most_common_question': most_common_question or 'No questions available'  # Default message if no questions
        })
    except Exception as e:
        print(f"Error fetching today's interactions: {e}")
        return jsonify({"error": "Failed to fetch today's interactions", "details": str(e)}), 500

@app.route('/admin/daily_report', methods=['GET'])
def daily_report():
    print("Received request for daily report")
    try:
        # Simulate a response for testing
        return jsonify({'total_inquiries_today': 10})
    except Exception as e:
        print(f"Error fetching daily report: {e}")
        return jsonify({"error": "Failed to fetch daily report", "details": str(e)}), 500
    
@app.route('/admin/monthly_report', methods=['GET'])
def monthly_report():
    try:
        # Get the current month and year
        now = datetime.now(pytz.timezone('Asia/Manila'))
        current_month = now.month
        current_year = now.year

        # Calculate the start and end of the month
        start_of_month = datetime(current_year, current_month, 1)
        if current_month == 12:
            end_of_month = datetime(current_year + 1, 1, 1)  # January of next year
        else:
            end_of_month = datetime(current_year, current_month + 1, 1)  # First day of next month

        # Query messages for the current month
        messages = db_session.query(Message).filter(
            Message.timestamp >= start_of_month,
            Message.timestamp < end_of_month
        ).all()

        # Initialize a list to hold counts for each day of the month
        days_count = [0] * 31  # Assuming a maximum of 31 days

        # Count messages for each day
        for msg in messages:
            day = msg.timestamp.day  # Get the day from the timestamp
            days_count[day - 1] += 1  # Increment the count for that day

        # Prepare the response data
        days = [str(i + 1) for i in range(31)]  # Days of the month as strings
        return jsonify({
            'days': days[:now.day],  # Only return days up to the current day
            'daily_counts': days_count[:now.day]  # Only return counts up to the current day
        })
    except Exception as e:
        print(f"Error fetching monthly report: {e}")
        return jsonify({"error": "Failed to fetch monthly report", "details": str(e)}), 500
    
@app.route('/admin/student_interactions', methods=['GET'])
def student_interactions():
    print("Received request for student interactions")
    try:
        # Simulate a response for testing
        return jsonify({
            'labels': ['Week 4', 'Week 3', 'Week 2', 'Week 1'],
            'data': [5, 10, 15, 20]
        })
    except Exception as e:
        print(f"Error fetching student interactions: {e}")
        return jsonify({"error": "Failed to fetch student interactions", "details": str(e)}), 500
@app.route('/admin/add_info', methods=['POST'])
def add_info():
    data = request.json
    info = data.get('info')

    if not info:
        return jsonify({'error': 'No information provided.'}), 400

    try:
        # Add the information to the global list
        bot_information.append(info)
        logging.info(f"Added information: {info}")  # Log the added information
        return jsonify({'message': 'Information added successfully!'}), 200
    except Exception as e:
        logging.error(f"Error adding information: {e}")
        return jsonify({'error': 'Failed to add information. Please try again later.'}), 500
if __name__ == '__main__':   

    serve(app, host='0.0.0.0', port=5000)
