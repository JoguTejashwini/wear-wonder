
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GEMINI_API_KEY was not found in .env")
    raise SystemExit(1)

client = genai.Client(api_key=api_key)

try:
    print("Sending a small test request to Gemini...")

    response = client.interactions.create(
        model="gemini-3.8-flash",
        input='Return JSON only with one key named "primary_topic" and value "jeans_and_tops".',
        generation_config={"thinking_level": "low"},
    )

    print("\nGemini response:")
    print(response.output_text)

except Exception as error:
    print("\nGemini request failed:")
    print(type(error).__name__, str(error))

finally:
    client.close()
