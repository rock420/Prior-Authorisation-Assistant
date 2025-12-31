from typing import List, Optional
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime

from ..integrations.document_service import document_search_tool
from ..models.document import DocumentType, DocumentMetadata


class DocumentSearchInput(BaseModel):
    document_type: Optional[DocumentType] = Field(
        None, 
        description="The type of document to search for (clinical_note, lab_result, imaging_report, letter_of_medical_necessity, etc.). If not specified, searches all document types."
    )
    keywords: Optional[List[str]] = Field(
        None, 
        description="Keywords to filter the document search (searches title, tags, summary)"
    )


@tool(
    description="Search Documents/Records for a patient like Lab results, Medical Images, Clinical Notes, etc. "
                "Returns metadata about matching documents. Can search all document types or filter by specific type.",
    args_schema=DocumentSearchInput
)
async def search_patient_documents(
    runtime: ToolRuntime, 
    document_type: Optional[DocumentType] = None, 
    keywords: Optional[List[str]] = None
) -> List[dict]:
    patient_id = runtime.context.get("patient_id")
    if not patient_id:
        return []
    
    results = []
    documents = document_search_tool.search_documents(
        patient_id=patient_id,
        document_type=document_type,
        keywords=keywords
    )
    
    for doc in documents:
        if doc.is_final:
            results.append({
                "document_id": doc.document_id,
                "title": doc.title,
                "document_type": doc.document_type.value if hasattr(doc.document_type, 'value') else str(doc.document_type),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "tags": doc.tags or [],
            })
    
    return results