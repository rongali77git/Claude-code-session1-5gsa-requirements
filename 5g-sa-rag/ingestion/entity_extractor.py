"""
ingestion/entity_extractor.py

Extracts structured entities from 5G SA requirement and test plan sections:
  - Requirement IDs   (REQ-SA-001, REQ-QOS-003, etc.)
  - Test Case IDs     (TC-001, TC-SA-042, etc.)
  - Feature tags      (Handover, QoS, Slicing, Authentication, etc.)
  - 5G NR entities    (AMF, SMF, UPF, gNB, UE, PDU Session, etc.)
  - Priority levels   (P0, P1, Critical, High, etc.)
  - Carrier names     (from CARRIER_PATTERNS)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
#  Patterns
# ─────────────────────────────────────────────────────────────────────────────

# Requirement IDs — flexible to handle various naming conventions
REQ_ID_PATTERN = re.compile(
    r"\b(REQ[-_][A-Z0-9]+[-_][A-Z0-9]+(?:[-_][A-Z0-9]+)*)\b",
    re.IGNORECASE,
)

# Test Case IDs
TC_ID_PATTERN = re.compile(
    r"\b(TC[-_][A-Z0-9]+(?:[-_][A-Z0-9]+)*)\b",
    re.IGNORECASE,
)

# Priority
PRIORITY_PATTERN = re.compile(
    r"\b(P[0-3]|Critical|High Priority|Medium Priority|Low Priority|Mandatory|Optional)\b",
    re.IGNORECASE,
)

# 5G NR core entities
NR_ENTITY_PATTERNS = {
    "AMF":         r"\bAMF\b",
    "SMF":         r"\bSMF\b",
    "UPF":         r"\bUPF\b",
    "gNB":         r"\bg[Nn][Bb]\b",
    "UE":          r"\bUE\b",
    "NRF":         r"\bNRF\b",
    "PCF":         r"\bPCF\b",
    "AUSF":        r"\bAUSF\b",
    "UDM":         r"\bUDM\b",
    "N2":          r"\bN2\b",
    "N3":          r"\bN3\b",
    "N4":          r"\bN4\b",
    "N6":          r"\bN6\b",
    "PDU Session": r"\bPDU\s+Session\b",
    "NSSAI":       r"\bNSSAI\b",
    "S-NSSAI":     r"\bS-NSSAI\b",
    "NG-RAN":      r"\bNG-RAN\b",
    "5GC":         r"\b5GC\b",
    "NAS":         r"\bNAS\b",
    "RRC":         r"\bRRC\b",
    "PDCP":        r"\bPDCP\b",
    "SDAP":        r"\bSDAP\b",
    "QoS Flow":    r"\bQoS\s+Flow\b",
    "SUPI":        r"\bSUPI\b",
    "SUCI":        r"\bSUCI\b",
}

# Feature / capability tags
FEATURE_PATTERNS = {
    "Handover":           r"\b(handover|HO|X2-HO|Xn-HO|inter-gNB)\b",
    "Authentication":     r"\b(authentication|AUSF|5G-AKA|EAP-AKA)\b",
    "Network Slicing":    r"\b(network.?slic|NSSAI|S-NSSAI|slice\s+selection)\b",
    "QoS":                r"\b(QoS|quality.of.service|5QI|DSCP|GBR|AMBR)\b",
    "Registration":       r"\b(registration|initial\s+reg|mobility\s+reg|periodic\s+reg)\b",
    "PDU Session":        r"\b(PDU\s+session|session\s+establishment|session\s+modification)\b",
    "Security":           r"\b(security|integrity\s+protection|ciphering|NAS\s+security)\b",
    "Idle Mode":          r"\b(idle.mode|RRC.?IDLE|paging|cell.reselection)\b",
    "Connected Mode":     r"\b(connected.mode|RRC.?CONNECTED|measurement\s+report)\b",
    "Emergency":          r"\b(emergency|IMS\s+emerg|112|911|E911)\b",
    "VoNR":               r"\b(VoNR|voice.over.NR|IMS.over.NR)\b",
    "Roaming":            r"\b(roam|VPLMN|HPLMN|visited\s+network)\b",
    "Power Management":   r"\b(power.saving|DRX|eDRX|PSM|RRC\s+inactive)\b",
    "URLLC":              r"\b(URLLC|ultra.reliable|low.latency)\b",
    "eMBB":               r"\b(eMBB|enhanced.mobile.broadband)\b",
    "mMTC":               r"\b(mMTC|massive.machine)\b",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedEntities:
    req_ids:       list[str] = field(default_factory=list)
    tc_ids:        list[str] = field(default_factory=list)
    priorities:    list[str] = field(default_factory=list)
    nr_entities:   list[str] = field(default_factory=list)   # AMF, SMF, etc.
    features:      list[str] = field(default_factory=list)   # Handover, QoS, etc.

    def to_dict(self) -> dict:
        return {
            "req_ids":     list(set(self.req_ids)),
            "tc_ids":      list(set(self.tc_ids)),
            "priorities":  list(set(self.priorities)),
            "nr_entities": list(set(self.nr_entities)),
            "features":    list(set(self.features)),
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Extractor
# ─────────────────────────────────────────────────────────────────────────────

class EntityExtractor:

    def extract(self, text: str) -> ExtractedEntities:
        result = ExtractedEntities()

        # Requirement IDs
        result.req_ids = [m.upper() for m in REQ_ID_PATTERN.findall(text)]

        # Test Case IDs
        result.tc_ids = [m.upper() for m in TC_ID_PATTERN.findall(text)]

        # Priorities
        result.priorities = [m.title() for m in PRIORITY_PATTERN.findall(text)]

        # 5G NR entities
        for name, pattern in NR_ENTITY_PATTERNS.items():
            if re.search(pattern, text):
                result.nr_entities.append(name)

        # Feature tags
        for feature, pattern in FEATURE_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                result.features.append(feature)

        return result

    def extract_req_to_tc_links(self, text: str) -> list[tuple[str, str]]:
        """
        Find explicit links like 'REQ-SA-001 is verified by TC-SA-001'.
        Returns list of (req_id, tc_id) tuples.
        """
        links = []
        # Pattern: REQ-... <some words> TC-...
        link_pattern = re.compile(
            r"(REQ[-_][A-Z0-9_-]+)\b.{0,80}?\b(TC[-_][A-Z0-9_-]+)",
            re.IGNORECASE | re.DOTALL,
        )
        for m in link_pattern.finditer(text):
            links.append((m.group(1).upper(), m.group(2).upper()))
        return links
