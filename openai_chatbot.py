# backend/openai_chatbot.py
import openai

openai.api_key = "your_openai_api_key"  # Replace this with your actual key

def get_ai_answer(question: str, user_doubt: str) -> str:
    prompt = f"""You are a helpful teaching assistant. A student was given the question:
    
    "{question}"
    
    They now have a doubt: "{user_doubt}"
    
    Please answer their doubt clearly and briefly."""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if you have access
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.5,
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        return f"An error occurred: {e}"
