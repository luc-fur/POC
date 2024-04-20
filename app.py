import os
import time
import base64
import re
import json
import streamlit as st
import openai  
#from openai.types.beta.threads import MessageContentImageFile
from tools import TOOL_MAP

# Retrieve environment variables
azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
azure_openai_key = os.environ.get("AZURE_OPENAI_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")

# Initialize OpenAI client
client = None
if azure_openai_endpoint and azure_openai_key:
    client = openai.AzureOpenAI(
        api_key=azure_openai_key,
        api_version="2024-02-15-preview",
        azure_endpoint=azure_openai_endpoint,
    )
else:
    client = openai.OpenAI(api_key=openai_api_key)

# Retrieve environment variables
assistant_id = os.environ.get("ASSISTANT_ID")
instructions = "You are a Customer support eginner of a software company. You answer clients' questions besed on technical documentation and customers' solution parameters"
#os.environ.get("RUN_INSTRUCTIONS", "")
assistant_title = os.environ.get("ASSISTANT_TITLE", "AI Support Center")
enabled_file_upload_message = False #os.environ.get("ENABLED_FILE_UPLOAD_MESSAGE", "Upload a file")

# Function to create a thread
def create_thread(content, file):
    messages = [
        {
            "role": "user",
            "content": content,
        }
    ]
    thread = client.beta.threads.create(messages=messages)
    return thread

# Function to create a message
def create_message(thread, content, file):
    file_ids = []
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=content
    )

# Function to create a run
def create_run(thread):
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant_id, instructions=instructions
    )
    return run

# Function to get message value list
def get_message_value_list(messages):
    messages_value_list = []
    for message in messages:
        message_content = ""
        print(message)
        message_content = message.content[0].text

        #remove annotation as 【25†source】
        string = "Sample【25†source】"
        regex_pattern = r"【.*?】"
        cleaned_message_content= re.sub(regex_pattern, '', message_content.value)

        messages_value_list.append(cleaned_message_content)
        return messages_value_list

# Function to get message list
def get_message_list(thread, run):
    completed = False
    while not completed:
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        print("run.status:", run.status)
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print("messages:", "\n".join(get_message_value_list(messages)))
        if run.status == "completed":
            completed = True
        elif run.status == "failed":
            break
        else:
            time.sleep(1)
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    return get_message_value_list(messages)

# Function to get response
def get_response(user_input, file):
    if "thread" not in st.session_state:
        st.session_state.thread = create_thread(user_input, file)
    else:
        create_message(st.session_state.thread, user_input, file)
    run = create_run(st.session_state.thread)
    run = client.beta.threads.runs.retrieve(
        thread_id=st.session_state.thread.id, run_id=run.id
    )
    while run.status == "in_progress":
        print("run.status:", run.status)
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread.id, 
            run_id=run.id
        )
        run_steps = client.beta.threads.runs.steps.list(
            thread_id=st.session_state.thread.id, 
            run_id=run.id
        )
        print("run_steps:", run_steps)
    if run.status == "requires_action":
        print("run.status:", run.status)
        run = execute_action(run, st.session_state.thread)
    return "\n".join(get_message_list(st.session_state.thread, run))

# Function to execute action
def execute_action(run, thread):
    tool_outputs = []
    for tool_call in run.required_action.submit_tool_outputs.tool_calls:
        tool_id = tool_call.id
        tool_function_name = tool_call.function.name
        print(tool_call.function.arguments)

        tool_function_arguments = json.loads(tool_call.function.arguments)

        print("id:", tool_id)
        print("name:", tool_function_name)
        print("arguments:", tool_function_arguments)

        tool_function_output = TOOL_MAP[tool_function_name](**tool_function_arguments)
        print("tool_function_output", tool_function_output)
        tool_outputs.append({"tool_call_id": tool_id, "output": tool_function_output})

    run = client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread.id,
        run_id=run.id,
        tool_outputs=tool_outputs,
    )
    return run

# Function to render chat messages
def render_chat():
    for chat in st.session_state.chat_log:
        with st.chat_message(chat["name"]):
            st.markdown(chat["msg"], True)


if "tool_call" not in st.session_state:
    st.session_state.tool_calls = []

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False


def disable_form():
    st.session_state.in_progress = True

# Main function
def main():
    st.title(assistant_title)
    user_msg = st.chat_input(
        "Message", on_submit=disable_form, disabled=st.session_state.in_progress
    )
    uploaded_file = None
    if user_msg:
        render_chat()
        with st.chat_message("user"):
            st.markdown(user_msg, True)
        st.session_state.chat_log.append({"name": "user", "msg": user_msg})
        file = None
        with st.spinner("Wait for response..."):
            response = get_response(user_msg, file)
        with st.chat_message("Assistant"):
            st.markdown(response, True)
        st.session_state.chat_log.append({"name": "assistant", "msg": response})
        st.session_state.in_progress = False
        st.session_state.tool_call = None
        st.rerun()
    render_chat()


if __name__ == "__main__":
    main()
