"""
GCP Workflows trigger — Infrastructure Layer

Fires a Cloud Workflows execution via the REST API using Application Default
Credentials (ADC).  In Cloud Run the service account provides credentials
automatically; locally, `gcloud auth application-default login` is required.
"""
import requests as _requests

from ...utils.logger import get_logger

logger = get_logger(__name__)


class GcpWorkflowTrigger:
    """Trigger a GCP Workflows execution."""

    BASE_URL = "https://workflowexecutions.googleapis.com/v1"

    def __init__(self, project_id: str, location: str, workflow_name: str):
        self.project_id = project_id
        self.location = location
        self.workflow_name = workflow_name

    def trigger(self) -> str:
        """
        Start a new workflow execution and return the execution resource name.

        Raises:
            RuntimeError: if the API call fails or credentials are unavailable.
        """
        try:
            import google.auth
            import google.auth.transport.requests as google_requests
        except ImportError as exc:
            raise RuntimeError(
                "google-auth is required to trigger GCP Workflows. "
                "Install it with: pip install google-auth"
            ) from exc

        try:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(google_requests.Request())
        except Exception as exc:
            raise RuntimeError(f"Failed to obtain GCP credentials: {exc}") from exc

        url = (
            f"{self.BASE_URL}/projects/{self.project_id}"
            f"/locations/{self.location}"
            f"/workflows/{self.workflow_name}/executions"
        )
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }
        resp = _requests.post(url, headers=headers, json={}, timeout=15)
        if not resp.ok:
            raise RuntimeError(
                f"GCP Workflows API error {resp.status_code}: {resp.text[:300]}"
            )

        execution_name = resp.json().get("name", "")
        logger.info(f"GCP Workflow execution started: {execution_name}")
        return execution_name
