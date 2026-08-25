"""Interactive Medical Copilot API powered by Gemini 2.5 Flash.

Provides interactive clinical reasoning, differential diagnosis, and Q&A
for examining physicians reviewing SmartLiva ultrasound studies.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google import genai

logger = logging.getLogger("SmartLiva.Copilot")

router = APIRouter(prefix="/api/v1/copilot", tags=["Medical Copilot"])


class CopilotMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class CopilotChatRequest(BaseModel):
    study_context: Optional[Dict[str, Any]] = None
    messages: List[CopilotMessage] = []
    question: Optional[str] = None


class CopilotChatResponse(BaseModel):
    reply: str
    suggested_actions: List[str] = []


SYSTEM_INSTRUCTION = """You are SmartLiva Copilot, an expert AI Clinical Hepatologist and Ultrasound Radiologist assistant.
Your goal is to assist attending physicians and sonographers in interpreting liver ultrasound findings, cross-referencing findings with clinical laboratory markers (AST, ALT, Bilirubin, AFP, Platelets) and patient risk history (raw fish consumption, alcohol, viral hepatitis).

Clinical Knowledge Guidelines:
1. Fibrosis: METAVIR stages F0-F4. Note that ultrasound B-mode stiffness estimates can be compressed by severe steatosis attenuation.
2. Steatosis: S0 (Normal), S1 (Mild), S2 (Moderate), S3 (Severe).
3. Lesions: Follow standard liver imaging reporting (LI-RADS logic). Differentiate benign cysts / hemangiomas from malignant HCC / CCA / metastases.
4. Fluke/CCA Risk: Opisthorchis viverrini causes periportal fibrosis and intrahepatic biliary dilation leading to Cholangiocarcinoma risk.

Tone & Style:
- Professional, concise, evidence-based, supportive of physician decision-making.
- Communicate in clear Thai mixed with standard medical English terminology.
- Provide actionable recommendations (e.g., CT Triphasic, MRI with Primovist, FibroScan, Stool concentration technique for ova, 6-month surveillance).
"""


@router.post("/chat", response_model=CopilotChatResponse)
async def chat_with_copilot(req: CopilotChatRequest) -> CopilotChatResponse:
    """Provide interactive clinical reasoning and answer doctor queries about the study."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return CopilotChatResponse(
            reply="ขออภัย ไม่พบการตั้งค่า GEMINI_API_KEY ในระบบ โปรดตั้งค่าตัวแปรสภาพแวดล้อม GEMINI_API_KEY เพื่อเปิดใช้งาน AI Copilot",
            suggested_actions=["ตั้งค่า GEMINI_API_KEY", "ดูผลการวิเคราะห์ทางคลินิก"],
        )

    try:
        client = genai.Client(api_key=api_key)

        context_str = ""
        if req.study_context:
            context_str = f"\n\n[Active Ultrasound Study Context]:\n{json.dumps(req.study_context, indent=2, ensure_ascii=False)}"

        conversation_prompt = f"{SYSTEM_INSTRUCTION}{context_str}\n\n[Doctor Consultation History]:\n"
        for m in req.messages:
            prefix = "Doctor" if m.role == "user" else "Copilot"
            conversation_prompt += f"{prefix}: {m.content}\n"

        if req.question and (not req.messages or req.messages[-1].content != req.question):
            conversation_prompt += f"Doctor: {req.question}\n"

        conversation_prompt += "Copilot: "

        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=conversation_prompt,
        )

        reply_text = result.text.strip() if result and result.text else "ไม่สามารถประมวลผลคำตอบได้ในขณะนี้"

        suggested = [
            "แนวทางการตรวจติดตาม (Follow-up Plan)",
            "ความเสี่ยง Cholangiocarcinoma (CCA)",
            "ความขัดแย้งของค่าพังผืดกับไขมันพอกตับ",
        ]

        return CopilotChatResponse(reply=reply_text, suggested_actions=suggested)

    except Exception as err:
        logger.error(f"Copilot chat failed: {err}")
        return CopilotChatResponse(
            reply=f"ขออภัย เกิดข้อผิดพลาดในการปรึกษา AI Copilot: {err}",
            suggested_actions=[],
        )
