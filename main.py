from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File, Form
import uuid

from pydantic import BaseModel
from fastapi.responses import FileResponse
from pathlib import Path

from .database import question_collection
import json
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = FastAPI()

# Base directory is backend folder
BASE_DIR = Path(__file__).resolve().parent
# static/ folder is outside backend, at project root
STATIC_DIR = BASE_DIR.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount it so files are served at /static/*
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.post("/upload_question")
async def upload_question(
    course: str = Form(...),
    exam: str = Form(...),
    pdf: UploadFile = File(...)
):
    # 1) Validate file type
    if pdf.content_type != "application/pdf":
      raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # 2) Build a safe file name and save in /static
    # Example path: static/BCSE_204L/CAT-1/<uuid>_originalname.pdf
    safe_course = course.replace("/", "_").replace("\\", "_").strip()
    safe_exam = exam.replace("/", "_").replace("\\", "_").strip()
    folder = STATIC_DIR / safe_course / safe_exam
    folder.mkdir(parents=True, exist_ok=True)

    unique = uuid.uuid4().hex[:8]
    original = Path(pdf.filename).name
    fname = f"{unique}_{original}"
    save_path = folder / fname

    with open(save_path, "wb") as f:
        f.write(await pdf.read())

    # 3) Build the public path used by the frontend (served by FastAPI /static)
    public_path = str(save_path).replace(str(STATIC_DIR), "").replace("\\", "/")
    if not public_path.startswith("/"):
        public_path = "/" + public_path
    public_url = f"/static{public_path}"

    # 4) Insert a document into Mongo
    # Your collection is expected to be called question_collection (as per your project)
    doc = {
        "Course Code": course,
        "Exam": exam,
        "Questions": public_url
    }
    try:
        question_collection.insert_one(doc)
    except Exception as e:
        # Cleanup file if DB insert fails
        try:
            os.remove(save_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"DB insert failed: {e}")

    return {"message": "Upload successful", "path": public_url}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return FileResponse(frontend_path)
 
 
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')


class ChatRequest(BaseModel):
    query: str
    course: str | None = None
    exam: str | None = None

@app.get("/get_courses")
def get_courses():
    courses = question_collection.distinct("Course Code")
    return {"courses": courses}


@app.get("/get_exams/{course_code}")
def get_exams(course_code: str):

    exams = question_collection.find({"Course Code": course_code})
    unique_exams = list(set(doc["Exam"] for doc in exams))

    return {"exams": unique_exams}


@app.get("/get_questions/{course_code}/{exam}")
def get_questions(course_code: str, exam: str):

    query = {"Course Code": course_code, "Exam": exam}
    questions_cursor = question_collection.find(query, {"_id": 0})
    questions = list(questions_cursor)
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found")

    return {"questions": questions}

@app.post("/chat")
def handle_chat(request: ChatRequest):
    context = ""
    if request.course and request.exam:
        query = {"Course Code": request.course, "Exam": request.exam}
        context_cursor = question_collection.find(query, {"_id": 0}).limit(5)
        context_list = list(context_cursor)
        if context_list:
            context = "Use the following information from the course material as context:\n"
            context += json.dumps(context_list)

    prompt = f"""
    You are a friendly and helpful AI tutor.
    Your goal is to answer student questions based on the provided context.
    If the context is empty or doesn't contain the answer, use your general knowledge but mention that the topic might not be in the specified course material.

    {context}

    Now, please answer this student's question: "{request.query}"
    """
    
    try:
        response = model.generate_content(prompt)
        return {"response": response.text}
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        raise HTTPException(status_code=500, detail="Failed to get response from AI model.")