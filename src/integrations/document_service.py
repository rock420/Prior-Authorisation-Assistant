from abc import ABC
from typing import Optional, List
from models.document import DocumentType, DocumentMetadata, RetrievedDocument


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
        document_type: DocumentType,
        keywords: Optional[List[str]] = None
    ) -> List[DocumentMetadata]:
        """Search for documents matching criteria"""
        return []
    
    def retrieve_document(
        self,
        document_id: str
    ) -> RetrievedDocument:
        """Retrieve full document content"""
        pass

document_search_tool = DocumentSourceTool()
