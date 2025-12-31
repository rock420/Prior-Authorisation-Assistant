import json
from abc import ABC
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from ..models.document import DocumentType, DocumentMetadata, RetrievedDocument


_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_json(filename: str) -> dict:
    """Load JSON file from mock data directory."""
    filepath = _DATA_DIR / filename
    if not filepath.exists():
        return {}
    with open(filepath) as f:
        return json.load(f)

"""
This tools should integrate with document sources. Ideally it would be an interface and there would be multiple
implementation of that interface to integrate with various data sources.

Also, we may want to conisder a more robust document matching engine using semantic search, ranking, freshness, limiting. 
Here, we are just mocking the search based on document metadata.
"""
class DocumentSourceTool(ABC):
    """document source integrations"""
    
    def search_documents(
        self,
        patient_id: str,
        document_type: Optional[DocumentType] = None,
        keywords: Optional[List[str]] = None
    ) -> List[DocumentMetadata]:
        documents = _load_json("documents.json").get("documents", {})
        results = []
        
        for doc_id, doc_data in documents.items():
            # Filter by patient_id
            if doc_data.get("patient_id") != patient_id:
                continue
            
            # Filter by document_type
            if document_type is not None:
                doc_type_str = doc_data.get("document_type", "")
                if doc_type_str != document_type.value:
                    continue
            
            # Filter by keywords (search in title, tags, summary)
            if keywords:
                searchable_text = " ".join([
                    doc_data.get("title", ""),
                    doc_data.get("summary", ""),
                    " ".join(doc_data.get("tags", []))
                ]).lower()
                
                if not any(kw.lower() in searchable_text for kw in keywords):
                    continue
            
            # Build DocumentMetadata
            try:
                created_at_str = doc_data.get("created_at", "")
                metadata = DocumentMetadata(
                    document_id=doc_data.get("document_id", doc_id),
                    patient_id=doc_data.get("patient_id"),
                    title=doc_data.get("title", ""),
                    document_type=DocumentType(doc_data.get("document_type", "clinical_note")),
                    document_path=doc_data.get("document_path", ""),
                    created_at=datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else datetime.utcnow(),
                    is_final=doc_data.get("is_final", True),
                    tags=doc_data.get("tags", [])
                )
                results.append(metadata)
            except (ValueError, TypeError) as e:
                # Skip documents with invalid data
                continue
        
        # Sort by created_at descending (most recent first)
        results.sort(key=lambda x: x.created_at, reverse=True)
        
        return results
    
    def retrieve_document(self, document_id: str) -> Optional[RetrievedDocument]:
        pass


document_search_tool = DocumentSourceTool()
