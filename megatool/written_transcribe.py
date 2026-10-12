"""Structure-aware transcription helpers for the handwritten notebook.

The notebook mixes several layouts — fundamental tables, sector lists, buy/sell
transaction sheets and settlement summaries — so a single generic parser would
destroy the information the owner actually kept. This module handles the two
*arithmetic* layouts (transactions and settlements), because those are the only
ones that can be checked independently of the handwriting:

  * a transaction line is ``SYMBOL -> qty x price -> amount``, so
    ``qty * price == amount`` is an internal check;
  * a settlement is ``buy total``, ``sell total``, ``net``, so
    ``|buy - sell| == |net|`` is an internal check.

Nothing here promotes a value to verified. A parse that cannot be checked is
kept and marked ``unreconcilable``; a parse that fails a check is kept and
marked ``discrepancy``. The module deliberately never re-reads a number to make
an equation balance — an alternative reading is recorded as a *hypothesis* for
a human to confirm against the page image, never applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from megatool.written_pdf import ReconciliationStatus, VerificationStatus

# ---------------------------------------------------------------------------
# The ONLY settlements in this document that carry a direct visual reading of
# the page image *and* a passing arithmetic check.
#
# Verified 2026-10-12 by reading data/written_pdf/raw_pages/page_21.png, then
# confirmed by subtraction. Each settlement on that page states three times
# over what it is worth - buy minus sell, the boxed "Net Payable", and the
# circled "Paid <amount> on <date>" - and all three agree for 9A-9D.
#
# Nothing else in the notebook is verified. Rows parsed from OCR elsewhere
# stay OCR_ONLY however well they balance: a balancing equation is evidence
# about a reading, never a substitute for looking at the page (see L-07).
# ---------------------------------------------------------------------------
VERIFIED_SETTLEMENTS: list[tuple[float, float, float]] = [
    (77_609.76, 12_059.43, 65_550.33),  # 9A
    (106_186.34, 88_169.68, 18_016.66),  # 9B
    (189_763.58, 157_168.39, 32_595.19),  # 9C
    (54_157.24, 45_035.39, 9_121.85),  # 9D
]

#: Page 21, read directly off ``raw_pages/page_21.png`` on 2026-10-12. Each
#: block writes one Buy line and one Sell line, so a column's single figure is
#: both its component and its total.
#:
#: These four share one key set with the page 19 and 23 records below — one
#: shape for every visually read settlement, so no consumer has to know which
#: page a record came from to read it.
VERIFIED_SETTLEMENT_DETAILS: list[dict[str, Any]] = [
    {
        "label": label,
        "page": 21,
        "dates": dates,
        "buy_components": [buy],
        "buy_total": buy,
        "buy_total_is_written": True,
        "sell_components": [sell],
        "sell_total": sell,
        "net": net,
        "direction": "payable",
        "settled": paid,
        "settled_label": "Paid",
        "settled_on": paid_on,
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_21.png on 2026-10-12; "
            f"{buy} - {sell} = {net} exactly, matching both the boxed Net "
            "Payable and the circled Paid annotation"
        ),
    }
    for label, dates, buy, sell, net, paid, paid_on in [
        ("9A", "11 sep / 1 sep", 77_609.76, 12_059.43, 65_550.33, 65_550.33, "12th Sep"),
        ("9B", "16 sep / 16 sep", 106_186.34, 88_169.68, 18_016.66, 18_016.66, "22nd Sep"),
        ("9C", "18 sep / 18 sep", 189_763.58, 157_168.39, 32_595.19, 32_595.19, "24th Sep"),
        ("9D", "22 sep / 22 sep", 54_157.24, 45_035.39, 9_121.85, 9_121.85, "25th Sep"),
    ]
]

#: Settlements read directly off ``raw_pages/page_19.png`` on 2026-10-12 and
#: checked line by line. Figures are the notebook's own, written exactly as they
#: appear. Two things on this page do not balance, and both are recorded as
#: facts about the source rather than repaired:
#:
#: * **8C's sell column is 1.00 short of its own components.** 154,824.76 +
#:   71,535.52 = 226,360.28, but the written total is 226,359.28. The notebook
#:   then takes its net from the *written* total, and that part is exact
#:   (226,359.28 − 168,147.83 = 58,211.45, matching the boxed figure), so the
#:   page is internally consistent about its own mistake.
#: * **8C's receipt is 8.03 below its net receivable** — received 58,203.42
#:   against 58,211.45. The page states both and explains neither. No cause is
#:   assumed here; a fee or a further slip would both look like this.
#:
#: 8E also carries the author's own correction: an earlier sell total of
#: 148,503.38 struck through, with 148,478.38 written beside it. The struck
#: reading is kept alongside the corrected one.
VISUALLY_READ_PAGE_19: list[dict[str, Any]] = [
    {
        "label": "8C",
        "page": 19,
        "dates": "13/14/18 Aug buy, 14/15 Aug sell",
        "buy_components": [52_445.75, 76_847.01, 38_855.07],
        "buy_total": 168_147.83,
        "buy_total_is_written": True,
        "sell_components": [154_824.76, 71_535.52],
        "sell_total": 226_359.28,  # as written; its components sum to 226,360.28
        "net": 58_211.45,
        "direction": "receivable",
        "settled": 58_203.42,
        "settled_label": "Received",
        "settled_on": "21 Aug",
        "components_ok": {"buy": True, "sell": False},
        "net_matches_written_totals": True,
        "source_discrepancies": [
            "sell components sum to 226360.28 but the written total is 226359.28 (1.00)",
            "received 58203.42 is 8.03 below the net receivable 58211.45",
        ],
        "superseded_readings": [],
        "ocr_notes": [],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_19.png on 2026-10-12; the sell gap and "
            "the 8.03 shortfall are both visible on the page and are reproduced "
            "here unaltered"
        ),
    },
    {
        "label": "8D",
        "page": 19,
        "dates": "25/27 Aug buy, 21/18 Aug sell",
        "buy_components": [84_240.63, 27_752.59],
        "buy_total": 111_993.22,
        "buy_total_is_written": True,
        "sell_components": [28_709.29, 82_466.14],
        "sell_total": 111_175.43,
        "net": 817.79,
        "direction": "payable",
        "settled": 817.79,
        "settled_label": "Paid",
        "settled_on": "Aug 28",
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_19.png on 2026-10-12; both columns add "
            "up exactly, 111993.22 - 111175.43 = 817.79 matches the boxed net and "
            "the circled Paid note"
        ),
    },
    {
        "label": "8E",
        "page": 19,
        "dates": "28/29 Aug buy, 25/28 Aug sell",
        "buy_components": [65_158.34, 152_336.94],
        "buy_total": 217_495.28,
        "buy_total_is_written": True,
        "sell_components": [23_847.10, 124_631.28],
        "sell_total": 148_478.38,
        "net": 69_016.90,
        "direction": "payable",
        "settled": 69_016.90,
        "settled_label": "Paid",
        "settled_on": "September 1st",
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "ocr_notes": [],
        "superseded_readings": [
            {
                "field": "sell_total",
                "original_reading": 148_503.38,
                "corrected_value": 148_478.38,
                "reason": (
                    "the author struck the earlier total out on the page and wrote "
                    "the corrected one beside it; both are kept"
                ),
            },
            {
                "field": "sell_components",
                "original_reading": 73_872.10,
                "corrected_value": 23_847.10,
                "reason": (
                    "the earlier figure is struck through on the page; the corrected "
                    "23,847.10 is what sums with 124,631.28 to the written total"
                ),
            },
        ],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_19.png on 2026-10-12; 217495.28 - "
            "148478.38 = 69016.90 matches the boxed net and the circled Paid note, "
            "and the superseded figures are visible under strike-through"
        ),
    },
]

#: Page 23, read directly off ``raw_pages/page_23.png`` on 2026-10-12.
#:
#: This page is the clearest evidence that refusing an ambiguous token beats
#: guessing at it: Vision returned the 9F sell figure as ``55, 642.285``, three
#: decimals, so :func:`parse_money` returned ``None``. Read off the page it is
#: 55,642.28, and 146,549.32 − 55,642.28 = 90,907.04 exactly, matching both the
#: boxed net and the circled Paid note. Had the token been guessed as
#: 55642285 or rounded to 55,642.29 the settlement could not have closed.
#:
#: 9E's buy total is not written separately on the page — the two buy entries
#: are bracketed and the net was taken from their sum — so ``buy_total`` here is
#: that sum, marked with ``buy_total_is_written`` false rather than passed off
#: as a figure the notebook contains.
VISUALLY_READ_PAGE_23: list[dict[str, Any]] = [
    {
        "label": "9E",
        "page": 23,
        "dates": "23/24 Sep buy, 24 Sep sell",
        "buy_components": [48_380.66, 73_513.46],
        "buy_total": 121_894.12,
        "buy_total_is_written": False,
        "sell_components": [81_793.82],
        "sell_total": 81_793.82,
        "net": 40_100.30,
        "direction": "payable",
        "settled": 40_100.30,
        "settled_label": "Paid",
        "settled_on": "29th September",
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_23.png on 2026-10-12; 48380.66 + "
            "73513.46 - 81793.82 = 40100.30, matching the boxed net and the "
            "circled Paid note"
        ),
    },
    {
        "label": "9F",
        "page": 23,
        "dates": "29 Sep buy, 23 Sep sell",
        "buy_components": [146_549.32],
        "buy_total": 146_549.32,
        "buy_total_is_written": True,
        "sell_components": [55_642.28],
        "sell_total": 55_642.28,
        "net": 90_907.04,
        "direction": "payable",
        "settled": 90_907.04,
        "settled_label": "Paid",
        "settled_on": "30 Sep",
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [
            "Vision returned the sell figure as '55, 642.285'; parse_money "
            "refused it as ambiguous, and the page reads 55,642.28"
        ],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_23.png on 2026-10-12; 146549.32 - "
            "55642.28 = 90907.04, matching the boxed net and the circled Paid note"
        ),
    },
]

#: Page 30, read directly off ``raw_pages/page_30.png`` on 2026-10-12.
#:
#: Three blocks — 12D, 12E, 12F. Before this read the page's 3 candidate blocks
#: and 20 unplaced figures had no human reading behind them at all; the parser
#: produced them from OCR and nobody had looked.
#:
#: The red Received/Paid annotations sit in small cursive clouds. 12E's was
#: legible and matches its net to the paisa. 12D's and 12F's were not, so
#: ``settled`` and ``settled_on`` are ``None`` — deliberately not transcribed
#: rather than guessed. A ``None`` here means "not read", never "zero".
VISUALLY_READ_PAGE_30: list[dict[str, Any]] = [
    {
        "label": "12D",
        "page": 30,
        "dates": "16/18/19/22 Dec buy, 16/18/19 Dec sell",
        "buy_components": [98_889.26, 95_841.88, 75_943.63, 12_782.66],
        "buy_total": 283_457.42,
        "buy_total_is_written": True,
        "sell_components": [105_891.72, 124_982.81, 196_245.12],
        "sell_total": 427_119.65,
        "net": 143_662.23,
        "direction": "receivable",
        "settled": None,
        "settled_label": "Received",
        "settled_on": None,
        "components_ok": {"buy": False, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [
            "buy components sum to 283457.43 but the written total is 283457.42 (0.01)",
        ],
        "superseded_readings": [],
        "ocr_notes": [
            "The 0.01 buy gap sits at the limit of what this scan resolves — a "
            "5 versus a 6 in the last digit of one component would produce it — "
            "so it may be a misread component rather than an error in the "
            "notebook. Both readings are kept as read; neither was changed to "
            "close the gap.",
            "The red Received cloud (amount and date) could not be resolved at "
            "this magnification. settled and settled_on are None by choice: "
            "nothing was guessed. Re-read the cloud before using this block.",
        ],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_30.png on 2026-10-12; sell "
            "components sum to 427119.65 exactly and 427119.65 - 283457.42 = "
            "143662.23 exactly. The Received annotation was NOT read — "
            "settled is None"
        ),
    },
    {
        "label": "12E",
        "page": 30,
        "dates": "24/26 Dec buy, 24 Dec sell",
        "buy_components": [63_953.84, 63_180.95],
        "buy_total": 127_134.79,
        "buy_total_is_written": True,
        "sell_components": [98_933.23],
        "sell_total": 98_933.23,
        "net": 28_201.56,
        "direction": "payable",
        "settled": 28_201.56,
        "settled_label": "Paid",
        "settled_on": "29 Dec",
        "components_ok": {"buy": True, "sell": True},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_30.png on 2026-10-12; 63953.84 + "
            "63180.95 = 127134.79 and 127134.79 - 98933.23 = 28201.56 "
            "exactly, matching the boxed Net Payable and the red Paid note"
        ),
    },
    {
        "label": "12F",
        "page": 30,
        "dates": "29/31 Dec buy, 29/31 Dec sell",
        "buy_components": [24_958.15, 131_261.64],
        "buy_total": 156_219.79,
        "buy_total_is_written": True,
        "sell_components": [],
        "sell_total": 142_725.91,
        "net": 13_493.88,
        "direction": "payable",
        "settled": None,
        "settled_label": "Paid",
        "settled_on": None,
        "components_ok": {"buy": True, "sell": False},
        "net_matches_written_totals": True,
        "source_discrepancies": [],
        "superseded_readings": [],
        "ocr_notes": [
            "The two sell line items were not resolved to reliable figures, so "
            "sell_components is empty rather than filled with a guess. The "
            "written sell total 142725.91 appears twice on the page — under "
            "the Sell column and inside the Net Payable calculation — and is "
            "what was read. components_ok.sell is False because there is "
            "nothing to check, not because a sum disagreed.",
            "The red Paid cloud (amount and date) could not be resolved at "
            "this magnification. settled and settled_on are None by choice. "
            "A figure reading 12557.57 appears elsewhere on the page but "
            "could not be tied to this annotation, so it is not recorded as "
            "the payment.",
        ],
        "verification_status": VerificationStatus.VERIFIED.value,
        "evidence": (
            "visual read of raw_pages/page_30.png on 2026-10-12; 24958.15 + "
            "131261.64 = 156219.79 exactly and 156219.79 - 142725.91 = "
            "13493.88 exactly. The sell components and the Paid annotation "
            "were NOT read — one list is empty, the other fields are None"
        ),
    },
]

#: Every settlement read off a page image so far, across pages.
ALL_VISUALLY_READ: list[dict[str, Any]] = [
    *VERIFIED_SETTLEMENT_DETAILS,
    *VISUALLY_READ_PAGE_19,
    *VISUALLY_READ_PAGE_23,
    *VISUALLY_READ_PAGE_30,
]

#: Pages from which at least one settlement has been read by eye.
VISUALLY_READ_PAGES: frozenset[int] = frozenset(d["page"] for d in ALL_VISUALLY_READ)

#: Every page whose image has actually been opened and looked at, whether or not
#: a settlement was transcribed from it.
#:
#: Page 20 is the reason this is tracked separately from
#: :data:`VISUALLY_READ_PAGES`: it carries no ``Settlement`` header, so nothing
#: is transcribed from it, but reading it confirmed two things. Its circled
#: day-total labels (8C, 8d, 8E) group the same dates into the same settlements
#: as page 19's blocks — an independent check of page 19's labels — and the
#: working copy's Index calls it "Settlement calculations and payable amounts"
#: when it is a transaction detail table of ``symbol -> qty x price``.
#:
#: Inspecting a page is not transcribing it. It stays out of
#: :data:`VISUALLY_READ_PAGES` because no record came off it.
VISUALLY_INSPECTED_PAGES: frozenset[int] = frozenset({19, 20, 21, 23, 30})

# Separators OCR commonly substitutes for a decimal point in this document:
# the notebook is handwritten, and Vision returns •, ·, - and , as readily as .
_DEC_SEPARATORS = ",.•·‧–—-"
_SEP_CLASS = re.escape(_DEC_SEPARATORS)


@dataclass
class TradeLine:
    """One ``SYMBOL -> qty x price -> amount`` line."""

    page: int
    symbol: str
    quantity: int
    price: float
    amount: float | None
    raw: str
    side: str = "buy"  # buy | sell | unknown (parentheses in the notebook mean sell)
    line_no: int = 0

    @property
    def computed_amount(self) -> float:
        return round(self.quantity * self.price, 2)

    @property
    def implied_price(self) -> float | None:
        """``amount / quantity`` — what the price must have been.

        The notebook always writes ``amount = quantity x price`` (checked on
        every line where both are legible). When a parsed line disagrees, the
        implied price on this document has consistently turned out to be a
        clean figure and the *price* the thing OCR misread, e.g. 350 x 159.60
        against a written 55,650 implies 159.00.

        It is recorded as a hypothesis for a human to confirm. Nothing here
        substitutes it into ``price`` — that would be re-reading the page by
        arithmetic, which is how a fabricated figure gets into a ledger.
        """
        if self.amount is None or self.quantity <= 0:
            return None
        return round(abs(self.amount) / self.quantity, 2)

    @property
    def reconciliation(self) -> ReconciliationStatus:
        if self.amount is None:
            return ReconciliationStatus.UNRECONCILABLE
        if abs(self.computed_amount - abs(self.amount)) <= 0.02:
            return ReconciliationStatus.RECONCILED
        return ReconciliationStatus.DISCREPANCY


@dataclass
class SettlementBlock:
    """One ``Settlement 9X`` block with its buy / sell / net figures.

    ``buy`` and ``sell`` hold every figure read from that column in page
    order; the notebook writes the individual amounts first and the written
    total last, so both the component sum and the total are available and can
    be checked against each other.
    """

    page: int
    label: str
    #: The label token exactly as OCR read it (``9Đ``, ``91``, ``""``).
    #: Never rewritten: a wrong reading is still evidence about the page.
    label_raw: str = ""
    #: ``ocr`` — Vision spelled the letter; ``position`` — assigned by the
    #: block's place among the page's blocks because the letter was unread.
    label_source: str = "ocr"
    buy: list[float] = field(default_factory=list)
    sell: list[float] = field(default_factory=list)
    #: Figures read from a block whose buy/sell marker OCR did not recognise.
    #: Kept rather than discarded — the notebook lays two columns side by side
    #: and Vision returns them as one stream, so the marker may be the only
    #: thing separating them. Nothing here is assigned to a column or used in
    #: any check until a reader places it.
    unplaced: list[float] = field(default_factory=list)
    net: float | None = None
    net_raw: str = ""
    paid: float | None = None
    direction: str = ""  # payable | receivable | ""
    raw_lines: list[str] = field(default_factory=list)
    line_nos: list[int] = field(default_factory=list)
    buy_total: float | None = None
    sell_total: float | None = None

    def _finalise(self) -> None:
        """Derive the written totals from the collected column figures."""
        self.buy_total = self.buy[-1] if self.buy else None
        self.sell_total = self.sell[-1] if self.sell else None

    # -- arithmetic checks ---------------------------------------------------
    @property
    def buy_sum(self) -> float | None:
        return round(sum(self.buy[:-1]), 2) if len(self.buy) > 1 else None

    @property
    def sell_sum(self) -> float | None:
        return round(sum(self.sell[:-1]), 2) if len(self.sell) > 1 else None

    @property
    def components_ok(self) -> bool | None:
        """Does the sum of a column's components equal its written total?"""
        checks = []
        if self.buy_sum is not None and self.buy_total is not None:
            checks.append(abs(self.buy_sum - self.buy_total) <= 0.02)
        if self.sell_sum is not None and self.sell_total is not None:
            checks.append(abs(self.sell_sum - self.sell_total) <= 0.02)
        return all(checks) if checks else None

    @property
    def computed_net(self) -> float | None:
        if self.buy_total is None or self.sell_total is None:
            return None
        return round(self.buy_total - self.sell_total, 2)

    @property
    def reference(self) -> float | None:
        """The figure the net is checked against: the written net, else the paid amount."""
        return self.net if self.net is not None else self.paid

    @property
    def reconciliation(self) -> ReconciliationStatus:
        computed = self.computed_net
        reference = self.reference
        if computed is None or reference is None:
            return ReconciliationStatus.UNRECONCILABLE
        if abs(abs(computed) - abs(reference)) <= 0.02:
            return ReconciliationStatus.RECONCILED
        return ReconciliationStatus.DISCREPANCY

    @property
    def fully_reconciled(self) -> bool:
        """Both the column sums and the net agree, where checkable."""
        return self.reconciliation is ReconciliationStatus.RECONCILED and (
            self.components_ok is not False
        )

    def as_dict(self) -> dict[str, Any]:
        computed = self.computed_net
        reference = self.reference
        return {
            "page": self.page,
            "label": self.label,
            "label_raw": self.label_raw,
            "label_source": self.label_source,
            "buy": self.buy,
            "sell": self.sell,
            "unplaced": self.unplaced,
            "buy_total": self.buy_total,
            "sell_total": self.sell_total,
            "buy_sum": self.buy_sum,
            "sell_sum": self.sell_sum,
            "components_ok": self.components_ok,
            "net": self.net,
            "net_raw": self.net_raw,
            "paid": self.paid,
            "direction": self.direction,
            "computed_net": computed,
            "reference": reference,
            "reference_is": "net"
            if self.net is not None
            else ("paid" if self.paid is not None else ""),
            "gap": (
                None
                if computed is None or reference is None
                else round(abs(computed) - abs(reference), 2)
            ),
            "reconciliation": self.reconciliation.value,
            "raw_lines": self.raw_lines,
            "line_nos": self.line_nos,
        }


def parse_money(raw: str) -> float | None:
    """Parse an OCR money token, or return ``None`` when it is ambiguous.

    OCR in this document writes a decimal point as `.`, `,`, `•`, `·` or `-`,
    and separates thousands inconsistently. The rule applied is: the *last*
    separator is a decimal point only when it is followed by one or two digits
    and every earlier group is at most three digits. Anything else is returned
    as ``None`` rather than guessed, because a silently-normalised settlement
    figure is worse than a missing one.

    ``None`` never means zero; callers must treat it as "unread".
    """
    text = raw.strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"\s", "", text)
    text = re.sub(r"(?i)\b(rs|npr|nrs)\b\.?", "", text)

    stripped = re.sub(rf"[^\d{_SEP_CLASS}]", "", text)
    if not any(ch.isdigit() for ch in stripped):
        return None

    parts = re.split(rf"([{_SEP_CLASS}])", stripped)
    digits = parts[0::2]
    seps = parts[1::2]
    if not seps:
        value = float("".join(digits))
    else:
        tail = digits[-1]
        head_groups = digits[:-1]
        if len(tail) == 3:
            # A three-digit tail is only unambiguous when the last separator is
            # a comma and the head is proper grouping: "117,142" is 117142.
            # A dot with a three-digit tail is refused ("642.285", "3.690"),
            # because reading it as 642285 or as 642.285 are equally plausible
            # and a settlement figure must never be chosen by luck.
            if seps[-1] == "," and all(len(g) <= 3 for g in head_groups):
                value = float("".join(digits))
            else:
                return None
        elif len(tail) in (1, 2):
            # One or two digits after the last separator is a decimal. The head
            # needs no grouping check when there is a single separator:
            # "38855,07" is 38855.07 even though the head is five digits.
            if len(seps) == 1 or all(len(g) <= 3 for g in head_groups):
                whole = "".join(head_groups) or "0"
                value = float(f"{whole}.{tail}")
            else:
                return None
        else:
            # Four or more trailing digits: not a price or a settlement amount
            # in this document, and not worth guessing at.
            return None
    return -value if negative else value


# A symbol is 2-7 letters, optionally with digits (e.g. "NABIL", "CBLBS", "9E").
_SYMBOL = r"[A-Z][A-Z0-9]{1,7}"
_ARROW = r"(?:→|-\s*>|>|➝)"


def parse_trade_line(line: str, page: int = 0, line_no: int = 0) -> TradeLine | None:
    """Parse ``SYMBOL -> qty x price -> [amount]``.

    Parenthesised quantities (``MANDU -> (60)x 1275.58``) are how the notebook
    marks sells, so they set ``side='sell'``. Returns ``None`` when the line is
    not recognisably a trade, so unrelated prose never becomes a record.
    """
    raw = line.rstrip()
    text = raw.upper()
    m = re.search(
        rf"({_SYMBOL})\s*(?:{_ARROW})?\s*[\(\[]?\s*(\d[\d,]*)\s*[\)\]]?\s*"
        rf"[xX×*]\s*([\d.,{_SEP_CLASS}]+)",
        text,
    )
    if not m:
        return None
    symbol = m.group(1)
    qty_raw, price_raw = m.group(2), m.group(3)
    if symbol in {"DATE", "BUY", "SELL", "SETTLEMENT"}:
        return None

    quantity = int(re.sub(r"\D", "", qty_raw) or 0)
    if quantity <= 0:
        return None
    price = parse_money(price_raw)
    if price is None or price <= 0:
        return None

    # The amount, if present, is the last number on the line after the price.
    tail = text[m.end() :]
    amount = None
    tail_nums = re.findall(rf"[\d{_SEP_CLASS}][\d.,{_SEP_CLASS}]*", tail)
    if tail_nums:
        amount = parse_money(tail_nums[-1])

    side = (
        "sell"
        if re.search(rf"{_SYMBOL}\s*(?:{_ARROW})?\s*[\(\[]\s*[\d,]+\s*[\)\]]", text)
        else "buy"
    )
    return TradeLine(
        page=page,
        symbol=symbol,
        quantity=quantity,
        price=price,
        amount=amount,
        raw=raw,
        side=side,
        line_no=line_no,
    )


_NET_HEAD = re.compile(r"(?:NET|NOT|Met|Net)\s*(?:PAYABLE|RECEIVABLE|PAYAB|RECEIV)?", re.IGNORECASE)
_PAID = re.compile(r"PAID|PAYED", re.IGNORECASE)

# Side markers as Vision actually returns them for this notebook. Cyrillic
# look-alikes are matched literally because regex IGNORECASE does not fold them.
_BUY_MARK = re.compile(r"\b(?:BUY|BY|Duy)\b|Вид|Вич|Виц|Bич", re.IGNORECASE)
_SELL_MARK = re.compile(r"S[EL5][L1I][L1I]|S[5E][NМ]|5EN|\bSEL\b|\b5EN\b|seM|Sol", re.IGNORECASE)
_NUM = re.compile(rf"[\d{_SEP_CLASS}][\d.,{_SEP_CLASS}]*")

#: A day-of-month written beside a month name, in the forms Vision returns for
#: this notebook — Latin or Cyrillic, because the pages mix both. Stripped
#: before money extraction: "13 Aug - 52,445.75" has one amount on it, not two.
#:
#: The lookarounds are load-bearing: without them the day pattern eats the last
#: two digits of an amount when a word follows it, turning
#: "11 sep - 77609.76 By" into "11 sep - 77609. By".
_DATE = re.compile(
    r"(?<![\d.,])\d{1,2}(?![\d.,])\s*[A-Za-zА-Яа-яЁё]{2,3}\b"  # 13 Aug, 18 Риз
    r"|(?<![\d.,])\d{1,2}(?![\d.,])(?:st|nd|rd|th)\b"  # 12th
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)

#: Whitespace Vision leaves inside a figure: "88 169.68", "226359. 28".
_SPLIT_FIGURE = re.compile(r"(?<=[\d.,])\s+(?=[\d.,])")

#: Floor for a figure accepted into a settlement's buy/sell column.
#:
#: The notebook's settlement totals and components are all at least 817.79
#: (the smallest seen, page 19's net), while the numbers Vision leaves between
#: them are days of the month and page numbers, all 31 or below. A day written
#: as "27" therefore cannot be a settlement figure, and 100 keeps every real
#: one. Excluded figures stay in ``raw_lines``, so nothing is discarded.
_SETTLEMENT_MIN = 100.0


def _strip_dates(line: str) -> str:
    """Remove day-of-month and month tokens, keeping the figures on the line."""
    return _DATE.sub(" ", line)


def _money_tokens(line: str) -> list[float]:
    """Every readable money token on a line, in order. Unreadable ones are dropped."""
    cleaned = _normalize_figures(line)
    return [v for v in (parse_money(t) for t in _NUM.findall(cleaned)) if v is not None]


def detect_settlement_label(line: str) -> str | None:
    """Canonical settlement label (``9A``..``9H``) if this line spells one out.

    Returns ``None`` when the letter is not a plain ``A``–``H``. Recognition
    mangles both the word ("Seltlement") and the letter ("9Đ", "91"), and
    mapping those glyphs onto letters produced confident wrong labels, so an
    unread letter stays unread here. :func:`find_block_starts` keeps the
    verbatim token regardless, and the caller assigns an unread label by the
    block's position on the page, recorded as such.
    """
    up = line.upper()
    m_stem = _STEM.search(up)
    if not m_stem:
        return None
    digit, letter = _ocr_series_and_letter(up[m_stem.end() :])
    if letter is None or digit is None:
        return None
    return f"{digit}{letter}"


#: The mangled word "settlement" as Vision writes it ("Seltlement", "setlement").
#: S, an E or L, an optional L, one or two T's, an optional L and E, then M.
_STEM = re.compile(r"S[EL]L?T{1,2}L?E?M")

#: A line that is only a label: ``8C``, ``9 E``, ``91``, or the misread ``84``.
_BARE_LABEL = re.compile(r"\s*(?:[98gG])\s*[A-ZĐ\d]\s*[:.-]?\s*", re.IGNORECASE)

#: A label token exactly as Vision wrote it, for the provenance record.
#: The lookbehind stops the 9 in "29 sep" from being read as a series digit.
_RAW_TOKEN = re.compile(r"(?<!\d)[98gG]\s*[A-ZĐ]", re.IGNORECASE)

#: The block letters the notebook uses. A read outside this set is not a label.
_LETTERS = "ABCDEFGH"


def _ocr_series_and_letter(raw: str) -> tuple[str | None, str | None]:
    """Month series digit and block letter — but only a letter Vision spelled.

    This refuses to guess, which is the whole point. Page 21's four headers
    come back as ``9Đ``, ``9 B``, ``91`` and nothing at all, and visually all
    four are 9A, 9B, 9C, 9D: ``Đ`` is not in A–H and ``1`` is a digit, so both
    return unread instead of being mapped to D and I the way a glyph rule would.
    """
    m = re.search(r"(?<!\d)([98gG])\s*([A-Z])", raw.upper())
    if not m:
        return None, None
    digit = "9" if m.group(1) == "G" else m.group(1)
    letter = m.group(2)
    if letter not in _LETTERS:
        return None, None
    return digit, letter


def _assign_labels(page: int, raws: list[str]) -> list[tuple[str, str, str]]:
    """``(label, verbatim token, source)`` for each block on one page.

    ``source`` is ``ocr`` only when Vision spelled the letter out; otherwise the
    label is derived from the block's position among the page's blocks and the
    source is ``position``. It is an identifier, never a value, and it stays
    marked as inferred so nobody later mistakes it for something transcribed.

    Position is measured from the first block whose letter *was* read, not from
    A, because a page does not necessarily begin at A: page 19's blocks are
    8C, 8D, 8E, while page 21's are 9A–9D. Anchoring on the first known letter
    recovers both. On page 21 that puts the unread first block at A (the known
    B sits at index 1), which matches what the page actually says.

    The series digit likewise comes from the first block whose letter was read;
    if none was, the label keeps a ``?`` series rather than borrowing one.
    """
    reads = [_ocr_series_and_letter(r) for r in raws]
    known = [(i, d, letter) for i, (d, letter) in enumerate(reads) if letter]
    series = known[0][1] if known else None
    anchor_index, anchor_letter = (known[0][0], known[0][2]) if known else (0, "A")

    out: list[tuple[str, str, str]] = []
    for i, raw in enumerate(raws):
        digit, letter = reads[i]
        if letter and (series is None or digit == series):
            out.append((f"{digit}{letter}", raw, "ocr"))
            continue
        offset = ord(anchor_letter) + (i - anchor_index)
        tail = chr(offset) if ord("A") <= offset <= ord("H") else "?"
        out.append((f"{series or '?'}{tail}", raw, "position"))
    return out


def find_block_starts(lines: list[str]) -> list[tuple[int, str]]:
    """``(1-based line number, verbatim label token)`` per settlement header.

    A pre-pass is the only way to handle Vision's three layouts without letting
    a header line leak into the preceding block's raw lines:

    * ``Settlement 9A`` on one line;
    * the word and its label split across two lines (``Setlement`` / ``8C``);
    * a bare repeat of a label already given (``Seltlement gE`` then ``9E``),
      which must not open a second block for the same settlement.

    A bare token counts only immediately after a stem line, so a stray number
    elsewhere can never start a block. A stem line whose next line is not a
    label still opens a block with an empty token — page 21's fourth block has
    no readable label at all, and dropping it would lose real figures.

    Tokens are returned verbatim: recognition's reading of a header is evidence
    too, and it is kept even when it is wrong.
    """
    starts: list[tuple[int, str]] = []
    pending: int | None = None
    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if _STEM.search(stripped.upper()):
            m = _RAW_TOKEN.search(stripped)
            if m:
                starts.append((i, m.group(0)))
                pending = None
            else:
                pending = i
            continue
        if pending is not None:
            token = stripped if _BARE_LABEL.fullmatch(stripped) else ""
            starts.append((pending, token))
            pending = None
            continue
        pending = None
    return starts


def _side_of(line: str) -> str:
    """Classify a line as buy / sell / net / paid / unknown."""
    if _PAID.search(line):
        return "paid"
    if _NET_HEAD.search(line):
        return "net"
    if _SELL_MARK.search(line):
        return "sell"
    if _BUY_MARK.search(line):
        return "buy"
    return "unknown"


def _normalize_figures(line: str) -> str:
    """Dates removed, then spaces *inside* a figure collapsed.

    Vision splits a number at its thousands boundary: "88 169.68" is 88169.68,
    "157 168.39" is 157168.39, "226359. 28" is 226359.28. Left split, each
    fragment is tokenised separately and the magnitude floor then keeps only the
    tail — silently recording 169.68 where the page says 88169.68.

    Collapsing is safe because parse_money validates grouping: a collapse that
    did join two genuinely separate figures would produce an ungroupable token
    and come back unread rather than as a wrong number.
    """
    return _SPLIT_FIGURE.sub("", _strip_dates(line))


def _net_from_line(line: str) -> float | None:
    """The figure a ``Net ...`` line states, or ``None`` when it is unclear.

    Two failures on real pages drive this:

    * ``Net receivate = 226359.28-168,4783 = 158, 211.43)`` — the net is the
      figure after the *last* ``=``, not the first number on the line. Taking
      the first gave 226359.28, which is a column total, not a net.
    * ``Net Payable 32595: 19)`` splits 32595.19 across a colon. Joining those
      tokens yields 3259519, a thousandfold error, so tokens are only rejoined
      when the OCR left a separator at the join. Otherwise the line comes back
      unread and the caller falls back to the notebook's own ``Paid`` note.
    """
    segment = line.rsplit("=", 1)[-1] if "=" in line else line
    tokens = _NUM.findall(_normalize_figures(segment))
    if not tokens:
        return None
    if len(tokens) == 1:
        return parse_money(tokens[0])
    if tokens[0][-1] in _SEP_CLASS or tokens[1][0] in _SEP_CLASS:
        return parse_money("".join(tokens))
    return None


def extract_settlements(page: int, text: str) -> list[SettlementBlock]:
    """Split a settlement page into blocks and pull out its figures.

    The notebook writes each settlement as a ``Settlement 9X`` header followed
    by two columns. Vision returns those columns as a flat sequence of lines,
    so a bare number inherits the last side marker seen above it — that is how
    the page is actually laid out, not a guess.

    Two independent arithmetic checks become possible:

    * within a column the final figure is the written total, so
      ``sum(components) == total``;
    * across columns ``|buy_total - sell_total| == |net|``.

    Failing either check never rewrites a figure; it marks the block
    ``discrepancy`` and keeps the raw lines as evidence.
    """
    blocks: list[SettlementBlock] = []
    lines = text.splitlines()
    starts = find_block_starts(lines)
    assigned = _assign_labels(page, [raw for _, raw in starts])

    for n, (header, _raw) in enumerate(starts):
        label, label_raw, source = assigned[n]
        # Content runs from the line after the header up to the next header.
        first = header  # 0-based index of the line after the header
        last = starts[n + 1][0] - 1 if n + 1 < len(starts) else len(lines)
        current = SettlementBlock(page=page, label=label, label_raw=label_raw, label_source=source)
        blocks.append(current)
        column = "unknown"
        # A bare figure sitting just before a "Paid" annotation for the same
        # amount is the net the notebook went on to pay; see the paid branch.
        pending_bare: tuple[list[float], int, str] | None = None

        for idx in range(first, last):
            stripped = lines[idx].strip()
            if not stripped:
                continue
            current.raw_lines.append(stripped)
            current.line_nos.append(idx + 1)

            side = _side_of(stripped)
            amounts = _money_tokens(stripped)
            prev_bare, pending_bare = pending_bare, None

            if side == "net":
                # The line is kept even when its figure is unread: page 21's
                # 9A net comes back as "65550.337", which parse_money refuses,
                # and the verbatim text is the evidence for a later review.
                current.net_raw = stripped
                value = _net_from_line(stripped)
                if value is not None:
                    current.net = value
                m = _NET_HEAD.search(stripped)
                if m and m.lastindex:
                    current.direction = (
                        "receivable" if "RECEIV" in m.group(1).upper() else "payable"
                    )
                continue
            if side == "paid":
                if amounts:
                    current.paid = amounts[0]
                    if current.net is None and prev_bare is not None:
                        figures, at, raw_bare = prev_bare
                        if at < len(figures) and abs(figures[at] - amounts[0]) <= 0.02:
                            # The notebook writes the net and then records the
                            # same figure as paid, so the match is corroboration
                            # from the page itself — not a value chosen to make
                            # an equation balance.
                            current.net = figures[at]
                            current.net_raw = raw_bare
                            del figures[at:]
                continue

            if side in ("buy", "sell"):
                column = side
                # A marker with no figure of its own is a column heading.
                if not amounts:
                    continue

            target = (
                current.buy
                if column == "buy"
                else current.sell
                if column == "sell"
                else current.unplaced
            )
            start = len(target)
            for amount in amounts:
                # Days and page numbers are not settlement figures; the raw
                # line still holds them for anyone rechecking the page.
                if amount >= _SETTLEMENT_MIN:
                    target.append(amount)
            if side == "unknown" and len(target) > start:
                pending_bare = (target, start, stripped)

    for b in blocks:
        b._finalise()
    return blocks


def summarise(blocks: list[SettlementBlock]) -> dict[str, int]:
    """Counts by reconciliation status, for a manifest or test assertion."""
    out: dict[str, int] = {}
    for b in blocks:
        out[b.reconciliation.value] = out.get(b.reconciliation.value, 0) + 1
    return out
