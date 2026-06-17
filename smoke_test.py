"""One-shot heartbeat: prove the full chain works end to end
(.env -> config -> OpenAI SDK -> network -> a real reply).

Run from the project root:
    uv run python smoke_test.py
"""

from openai import OpenAI

import config  # importing this loads .env and validates OPENAI_API_KEY

# The SDK automatically reads OPENAI_API_KEY from the environment that
# `import config` just populated, so we don't pass the key in by hand.
client = OpenAI()

response = client.chat.completions.create(
    model=config.DEFAULT_CHAT_MODEL,
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {
            "role": "user",
            "content": (
                "Reply with 'Connection OK' and then one short fun fact "
                "about plasma etching in semiconductor manufacturing."
            ),
        },
    ],
)

print(response.choices[0].message.content)
