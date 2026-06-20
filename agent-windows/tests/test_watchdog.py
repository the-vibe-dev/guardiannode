from __future__ import annotations

from src import watchdog


def test_parse_quser_active_sessions():
    output = """ USERNAME              SESSIONNAME        ID  STATE   IDLE TIME  LOGON TIME
>kid                  console             1  Active      none   6/20/2026 9:00 AM
 other                                     2  Disc           4   6/20/2026 8:00 AM
 parent               rdp-tcp#12           3  Active         .   6/20/2026 9:05 AM
"""
    assert watchdog._parse_quser_session_ids(output) == {1, 3}


def test_parse_tasklist_session_ids():
    output = (
        '"GuardianNodeAgent.exe","1000","Console","1","42,000 K"\n'
        '"GuardianNodeAgent.exe","1001","RDP-Tcp#12","3","41,000 K"\n'
    )
    assert watchdog._parse_tasklist_session_ids(output) == {1, 3}
