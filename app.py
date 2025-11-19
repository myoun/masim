import streamlit as st
from agent import app, State, Command, Interruption, AgentState, logger
from langchain.messages import HumanMessage
import uuid
import time
from enum import Enum

st.set_page_config(page_title="Masim Agent", layout="wide")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_state" not in st.session_state:
    st.session_state.agent_state = AgentState.IDLE

if "last_interrupt_value" not in st.session_state:
    st.session_state.last_interrupt_value = None

thread_id = st.session_state.thread_id
config = {"configurable": {"thread_id": thread_id}}

st.title("Masim Agent Web Interface")

# Sidebar for debug info
with st.sidebar:
    st.write(f"**Session ID:** `{thread_id}`")
    if st.button("Reset Session"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.agent_state = AgentState.IDLE
        st.session_state.last_interrupt_value = None
        st.rerun()

# Chat Interface
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

def process_stream(stream_generator):
    try:
        for event in stream_generator:
            logger.info(event)
            if "__interrupt__" in event:
                interrupts = event["__interrupt__"]
                if interrupts:
                    st.session_state.last_interrupt_value = interrupts[0].value
                    
                    # Handle Enum based interrupts
                    if interrupts[0].value == Interruption.PLAN_REVIEW:
                        st.session_state.agent_state = AgentState.PLAN_REVIEW
                    elif interrupts[0].value == Interruption.HUMAN_REVIEW_CONFIRM:
                        st.session_state.agent_state = AgentState.HUMAN_REVIEW_CONFIRM
                    elif interrupts[0].value == Interruption.HUMAN_REVIEW_COMMENT:
                        st.session_state.agent_state = AgentState.HUMAN_REVIEW_COMMENT
                    else:
                        st.session_state.agent_state = AgentState.INTERRUPTED
                    return
            
            # Update status based on current node
            for node_name, node_output in event.items():
                if node_name == "goal_extractor":
                    pass  # Silent
                elif node_name == "planning_agent":
                    plans_text = "\n".join([f"{i+1}. **{p['title']}**: {p['description']}" for i, p in enumerate(node_output['plans'])])
                    with st.chat_message("assistant"):
                        st.markdown(f"**계획 수립 완료:**\n\n{plans_text}")
                    st.session_state.messages.append({"role": "assistant", "content": f"**계획 수립 완료:**\n\n{plans_text}"})
                elif node_name == "plan_reviser":
                    plans_text = "\n".join([f"{i+1}. **{p['title']}**: {p['description']}" for i, p in enumerate(node_output['plans'])])
                    with st.chat_message("assistant"):
                        st.markdown(f"**수정된 계획:**\n\n{plans_text}")
                    st.session_state.messages.append({"role": "assistant", "content": f"**수정된 계획:**\n\n{plans_text}"})
                elif node_name == "coding_agent":
                    pass  # Silent
                elif node_name == "code_runner":
                    if node_output.get("output_path"):
                        st.video(node_output["output_path"])
                        st.session_state.messages.append({"role": "assistant", "content": f"비디오 생성 완료: {node_output['output_path']}"})
                elif node_name == "code_analyzer":
                    pass  # Silent
                elif node_name == "fix_planner":
                    pass  # Silent
                elif node_name == "fix_coding_agent":
                    pass  # Silent
        
        st.session_state.agent_state = AgentState.IDLE

    except Exception as e:
        st.error(f"Error: {e}")
        st.session_state.agent_state = AgentState.IDLE

# Input handling
if st.session_state.agent_state == AgentState.IDLE:
    user_input = st.chat_input("목표를 입력하세요...")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        with st.spinner("처리 중..."):
            try:
                logger.debug("Initializing State...")
                data = State(session_id=thread_id, messages=[HumanMessage(user_input)], max_retry=5, retry=0)
                logger.debug(f"invoking app with input: {user_input}")
                stream = app.stream(data, config=config)
                process_stream(stream)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
                st.session_state.agent_state = AgentState.IDLE
        
        st.rerun()

elif st.session_state.agent_state == AgentState.PLAN_REVIEW:
    st.write("### 계획 검토")
    
    # Get current plans from state
    current_state = app.get_state(config)
    plans = current_state.values.get("plans", [])
    
    # Check if form was submitted in session state
    if "plan_form_submitted" not in st.session_state:
        st.session_state.plan_form_submitted = False
    
    if not st.session_state.plan_form_submitted:
        feedbacks = []
        with st.form("plan_review_form"):
            for i, plan in enumerate(plans):
                st.markdown(f"**{i+1}. {plan['title']}**")
                st.write(plan['description'])
                feedback = st.text_input(f"피드백 (단계 {i+1})", key=f"feedback_{i}")
                feedbacks.append(f"단계 {i+1}: {feedback}" if feedback else "")
                st.divider()
            
            submitted = st.form_submit_button("제출")
            skipped = st.form_submit_button("건너뛰기")
            
            if submitted:
                st.session_state.plan_form_submitted = True
                # Aggregate feedback
                full_feedback = "\n".join(filter(None, feedbacks))
                
                if full_feedback:
                    st.session_state.messages.append({"role": "user", "content": f"**계획 피드백:**\n{full_feedback}"})
                else:
                    st.session_state.messages.append({"role": "user", "content": "계획 승인"})
                
                st.session_state.agent_state = AgentState.RUNNING
                
                with st.spinner("처리 중..."):
                    try:
                        stream = app.stream(Command(resume=full_feedback), config=config)
                        process_stream(stream)
                    except Exception as e:
                        logger.error(f"An error occurred: {e}")
                        st.error(f"An error occurred: {e}")
                        st.session_state.agent_state = AgentState.IDLE
                
                st.session_state.plan_form_submitted = False
                st.rerun()
            
            if skipped:
                st.session_state.plan_form_submitted = True
                st.session_state.agent_state = AgentState.RUNNING
                with st.spinner("처리 중..."):
                    try:
                        stream = app.stream(Command(resume=""), config=config)
                        process_stream(stream)
                    except Exception as e:
                        logger.error(f"An error occurred: {e}")
                        st.error(f"An error occurred: {e}")
                        st.session_state.agent_state = AgentState.IDLE
                
                st.session_state.plan_form_submitted = False
                st.rerun()

elif st.session_state.agent_state == AgentState.HUMAN_REVIEW_CONFIRM:
    st.write("### 수정사항이 있습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("예 (Y)"):
            st.session_state.messages.append({"role": "user", "content": "예"})
            st.session_state.agent_state = AgentState.RUNNING
            with st.spinner("처리 중..."):
                try:
                    stream = app.stream(Command(resume="Y"), config=config)
                    process_stream(stream)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    st.error(f"An error occurred: {e}")
                    st.session_state.agent_state = AgentState.IDLE
    with col2:
        if st.button("아니오 (N)"):
            st.session_state.messages.append({"role": "user", "content": "아니오"})
            st.session_state.agent_state = AgentState.RUNNING
            with st.spinner("처리 중..."):
                try:
                    stream = app.stream(Command(resume="N"), config=config)
                    process_stream(stream)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    st.error(f"An error occurred: {e}")
                    st.session_state.agent_state = AgentState.IDLE

elif st.session_state.agent_state == AgentState.HUMAN_REVIEW_COMMENT:
    st.write("### 수정 요청 사항")
    with st.form("human_review_form"):
        request = st.text_area("수정 내용을 입력하세요")
        submitted = st.form_submit_button("제출")
        
        if submitted:
            st.session_state.messages.append({"role": "user", "content": f"수정 요청: {request}"})
            st.session_state.agent_state = AgentState.RUNNING
            with st.spinner("처리 중..."):
                try:
                    stream = app.stream(Command(resume=request), config=config)
                    process_stream(stream)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    st.error(f"An error occurred: {e}")
                    st.session_state.agent_state = AgentState.IDLE

elif st.session_state.agent_state == AgentState.INTERRUPTED:
    with st.chat_message("assistant"):
        st.write(st.session_state.last_interrupt_value)
    
    with st.form("interrupt_form"):
        user_response = st.text_input("응답 입력")
        submitted = st.form_submit_button("전송")
        
        if submitted:
            st.session_state.messages.append({"role": "user", "content": user_response})
            st.session_state.agent_state = AgentState.RUNNING
            
            with st.spinner("처리 중..."):
                try:
                    stream = app.stream(Command(resume=user_response), config=config)
                    process_stream(stream)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    st.error(f"An error occurred: {e}")
                    st.session_state.agent_state = AgentState.IDLE

else:
    st.warning(f"Unknown or stuck state: {st.session_state.agent_state}")
    if st.button("Reset State"):
        st.session_state.agent_state = AgentState.IDLE
        st.rerun()
