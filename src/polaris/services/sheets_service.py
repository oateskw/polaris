"""Google Sheets integration for outreach tracking."""

from datetime import date, datetime, timedelta
from typing import Any, Optional

from polaris.config import Settings, get_settings

PROSPECTS_TAB = "Prospects"
DAILY_LOG_TAB = "Daily Log"

PROSPECT_HEADERS = [
    "Date", "Handle", "Business Name", "Type", "Location",
    "Followers", "Email", "DM Sent", "Replied", "Reply Date", "Stage", "Notes", "Follow-up Date",
]
DAILY_LOG_HEADERS = ["Date", "DMs Sent", "Replies", "Calls Booked", "Notes"]


class SheetsService:
    """Read/write the Polaris Outreach Google Sheet."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        import os
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        token_file = self.settings.google_sheets_token_file
        secrets_file = self.settings.google_sheets_client_secrets_file

        creds = None
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(secrets_file, scopes)
                creds = flow.run_local_server(port=0)
            with open(token_file, "w") as f:
                f.write(creds.to_json())

        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def _sheet_id(self) -> str:
        return self.settings.google_sheets_spreadsheet_id

    def _read(self, range_: str) -> list[list[str]]:
        result = (
            self._get_service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self._sheet_id(), range=range_)
            .execute()
        )
        return result.get("values", [])

    def _append(self, range_: str, values: list[list[Any]]) -> None:
        self._get_service().spreadsheets().values().append(
            spreadsheetId=self._sheet_id(),
            range=range_,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def _update(self, range_: str, values: list[list[Any]]) -> None:
        self._get_service().spreadsheets().values().update(
            spreadsheetId=self._sheet_id(),
            range=range_,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def ensure_headers(self) -> None:
        """Write headers to both tabs if they don't exist yet."""
        for tab, headers in [
            (PROSPECTS_TAB, PROSPECT_HEADERS),
            (DAILY_LOG_TAB, DAILY_LOG_HEADERS),
        ]:
            rows = self._read(f"{tab}!A1:Z1")
            if not rows or rows[0] != headers:
                self._update(f"{tab}!A1", [headers])

    # ------------------------------------------------------------------
    # Prospects
    # ------------------------------------------------------------------

    def add_prospect(
        self,
        handle: str,
        business_name: str,
        business_type: str,
        location: str,
        followers: str = "",
        email: str = "",
        notes: str = "",
    ) -> None:
        """Append a new prospect row and increment today's DM count."""
        today = date.today().strftime("%Y-%m-%d")
        row = [
            today,          # Date
            handle,         # Handle
            business_name,  # Business Name
            business_type,  # Type
            location,       # Location
            followers,      # Followers
            email,          # Email
            "Yes",          # DM Sent
            "No",           # Replied
            "",             # Reply Date
            "Contacted",    # Stage
            notes,          # Notes
            "",             # Follow-up Date
        ]
        self._append(f"{PROSPECTS_TAB}!A:M", [row])
        self._increment_dms_today()

    def get_pipeline(self) -> dict[str, int]:
        """Return count of prospects per stage."""
        rows = self._read(f"{PROSPECTS_TAB}!A:L")
        if len(rows) < 2:
            return {}
        stage_col = PROSPECT_HEADERS.index("Stage")
        counts: dict[str, int] = {}
        for row in rows[1:]:
            stage = row[stage_col] if len(row) > stage_col else "Unknown"
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def get_all_prospects(self) -> list[dict[str, str]]:
        """Return all prospect rows as dicts."""
        rows = self._read(f"{PROSPECTS_TAB}!A:L")
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [
            {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            for row in rows[1:]
        ]

    # ------------------------------------------------------------------
    # Daily Log
    # ------------------------------------------------------------------

    def _increment_dms_today(self) -> None:
        today_str = date.today().strftime("%Y-%m-%d")
        rows = self._read(f"{DAILY_LOG_TAB}!A:E")
        headers = rows[0] if rows else DAILY_LOG_HEADERS

        date_col = headers.index("Date") if "Date" in headers else 0
        dms_col = headers.index("DMs Sent") if "DMs Sent" in headers else 1

        # Find today's row (1-indexed, row 1 = headers)
        for i, row in enumerate(rows[1:], start=2):
            if row and row[date_col] == today_str:
                current = int(row[dms_col]) if len(row) > dms_col and row[dms_col] else 0
                col_letter = chr(ord("A") + dms_col)
                self._update(f"{DAILY_LOG_TAB}!{col_letter}{i}", [[current + 1]])
                return

        # Today not found — create the row
        new_row = [""] * len(headers)
        new_row[date_col] = today_str
        new_row[dms_col] = "1"
        self._append(f"{DAILY_LOG_TAB}!A:E", [new_row])

    def log_reply(self, handle: str) -> None:
        """Increment today's reply count and update prospect stage to Replied."""
        today_str = date.today().strftime("%Y-%m-%d")
        rows = self._read(f"{DAILY_LOG_TAB}!A:E")
        if not rows:
            return
        headers = rows[0]
        date_col = headers.index("Date") if "Date" in headers else 0
        replies_col = headers.index("Replies") if "Replies" in headers else 2

        for i, row in enumerate(rows[1:], start=2):
            if row and row[date_col] == today_str:
                current = int(row[replies_col]) if len(row) > replies_col and row[replies_col] else 0
                col_letter = chr(ord("A") + replies_col)
                self._update(f"{DAILY_LOG_TAB}!{col_letter}{i}", [[current + 1]])
                break

        # Update prospect stage
        prospect_rows = self._read(f"{PROSPECTS_TAB}!A:L")
        if len(prospect_rows) < 2:
            return
        p_headers = prospect_rows[0]
        handle_col = p_headers.index("Handle") if "Handle" in p_headers else 1
        stage_col = p_headers.index("Stage") if "Stage" in p_headers else 9
        reply_date_col = p_headers.index("Reply Date") if "Reply Date" in p_headers else 8
        replied_col = p_headers.index("Replied") if "Replied" in p_headers else 7

        for i, row in enumerate(prospect_rows[1:], start=2):
            if row and len(row) > handle_col and row[handle_col].lstrip("@") == handle.lstrip("@"):
                col_stage = chr(ord("A") + stage_col)
                col_reply_date = chr(ord("A") + reply_date_col)
                col_replied = chr(ord("A") + replied_col)
                self._update(f"{PROSPECTS_TAB}!{col_replied}{i}", [["Yes"]])
                self._update(f"{PROSPECTS_TAB}!{col_reply_date}{i}", [[today_str]])
                self._update(f"{PROSPECTS_TAB}!{col_stage}{i}", [["Replied"]])
                break

    def get_daily_stats(self, days: int = 7) -> list[dict[str, str]]:
        """Return daily log rows for the last N days."""
        rows = self._read(f"{DAILY_LOG_TAB}!A:E")
        if len(rows) < 2:
            return []
        headers = rows[0]
        cutoff = (date.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        results = []
        for row in rows[1:]:
            if not row:
                continue
            row_date = row[0] if row else ""
            if row_date >= cutoff:
                results.append(
                    {headers[i]: (row[i] if i < len(row) else "0") for i in range(len(headers))}
                )
        return sorted(results, key=lambda r: r.get("Date", ""))
