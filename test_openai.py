import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def test_openai_api():
    try:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            return {
                "success": False,
                "error": "OPENAI_API_KEY is missing from .env"
            }

        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model="gpt-5",
            input="Reply with exactly: OpenAI API connection successful."
        )

        return {
            "success": True,
            "model": "gpt-5",
            "response": response.output_text
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

print(test_openai_api())