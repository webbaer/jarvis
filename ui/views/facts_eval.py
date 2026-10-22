from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.client import ApiClient
from ui.views.common import call

DEFAULT_EVAL_K = 6
MAX_EVAL_K = 50
_SUPERSEDED_STYLE = "color: #8a8a8a; text-decoration: line-through;"


def render(client: ApiClient) -> None:
    st.subheader("Fakten")
    _facts(client)
    st.divider()
    st.subheader("Eval")
    _eval(client)


# --- facts -----------------------------------------------------------------

def _fact_frame(facts: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": f["id"],
                "Subjekt": f["subject"],
                "Attribut": f["attribute"],
                "Wert": f["value"],
                "Quelle": f["source"],
                "Gueltig ab": f["valid_from"][:19].replace("T", " "),
                "Gueltig bis": (f["valid_to"] or "")[:19].replace("T", " "),
                "Status": "aktiv" if f["status"] == "active" else "abgeloest",
            }
            for f in facts
        ]
    )


def _show_facts(facts: list[dict]) -> None:
    if not facts:
        st.caption("Keine Fakten.")
        return
    frame = _fact_frame(facts)
    styled = frame.style.apply(
        lambda row: [_SUPERSEDED_STYLE if row["Status"] == "abgeloest" else ""] * len(row), axis=1
    )
    st.dataframe(styled, hide_index=True, width="stretch")


def _fact_label(fact: dict) -> str:
    return f"{fact['subject']}.{fact['attribute']} = {fact['value']} (#{fact['id']})"


def _facts(client: ApiClient) -> None:
    show_all = st.toggle("Abgeloeste Versionen mit anzeigen", key="fe_show_all")
    facts = call(lambda: client.facts(include_superseded=show_all), "Fakten laden")
    if facts is None:
        return
    _show_facts(facts)
    active = [f for f in facts if f["status"] == "active"]

    col_new, col_edit = st.columns(2)
    with col_new, st.form("fe_new_fact", clear_on_submit=True):
        st.markdown("**Neuer Fakt**")
        subject = st.text_input("Subjekt")
        attribute = st.text_input("Attribut")
        value = st.text_input("Wert")
        source = st.text_input("Quelle")
        valid_from = st.text_input("Gueltig ab (optional, ISO-Datum)")
        st.caption("Gibt es schon einen aktiven Fakt mit gleichem Subjekt und Attribut, wird er abgeloest.")
        if st.form_submit_button("Anlegen"):
            if not all(v.strip() for v in (subject, attribute, value, source)):
                st.error("Subjekt, Attribut, Wert und Quelle sind Pflichtfelder.")
            elif call(lambda: client.create_fact(subject, attribute, value, source, valid_from or None), "Anlegen"):
                st.rerun()

    with col_edit:
        st.markdown("**Fakt aendern** (alte Version bleibt als abgeloest erhalten)")
        if not active:
            st.caption("Keine aktiven Fakten.")
        else:
            fact = st.selectbox("Fakt", active, format_func=_fact_label, key="fe_edit_fact")
            with st.form("fe_edit_form", clear_on_submit=True):
                new_value = st.text_input("Neuer Wert", value=fact["value"])
                new_source = st.text_input("Quelle der Aenderung")
                new_valid_from = st.text_input("Gueltig ab (optional)")
                if st.form_submit_button("Neue Version speichern"):
                    if not new_value.strip() or not new_source.strip():
                        st.error("Wert und Quelle sind Pflichtfelder.")
                    elif call(
                        lambda: client.update_fact(fact["id"], new_value, new_source, new_valid_from or None),
                        "Aendern",
                    ):
                        st.rerun()

    st.markdown("**Historie**")
    all_facts = facts if show_all else call(lambda: client.facts(include_superseded=True), "Fakten laden") or []
    if all_facts:
        fact = st.selectbox("Fakt", all_facts, format_func=_fact_label, key="fe_history_fact")
        history = call(lambda: client.fact_history(fact["id"]), "Historie laden")
        if history is not None:
            _show_facts(history)


# --- eval ------------------------------------------------------------------

def _flatten(config: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in config.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = str(value)
    return flat


def _run_label(run: dict) -> str:
    return f"#{run['id']} · {run['created_at'][:19].replace('T', ' ')} · k={run['k']}"


def _eval(client: ApiClient) -> None:
    col_k, col_btn = st.columns([1, 3])
    k = col_k.number_input("k", min_value=1, max_value=MAX_EVAL_K, value=DEFAULT_EVAL_K, key="fe_eval_k")
    if col_btn.button("Eval-Lauf starten", type="primary"):
        with st.spinner("Eval laeuft ..."):
            run = call(lambda: client.run_eval(int(k)), "Eval")
        if run is not None:
            st.session_state["fe_last_run"] = run["id"]
            st.rerun()

    runs = call(client.eval_results, "Eval-Ergebnisse laden")
    if not runs:
        if runs is not None:
            st.caption("Noch keine Eval-Laeufe.")
        return

    latest = runs[0]
    cols = st.columns(3)
    cols[0].metric(f"Recall@{latest['k']}", f"{latest['recall_at_k']:.3f}")
    cols[1].metric("MRR", f"{latest['mrr']:.3f}")
    cols[2].metric("Faelle", latest["cases"])
    st.caption(f"Letzter Lauf {_run_label(latest)} · Datensatz {latest['dataset']}")

    st.markdown("**Alle Laeufe**")
    st.dataframe(
        [
            {
                "Lauf": f"#{r['id']}",
                "Zeit": r["created_at"][:19].replace("T", " "),
                "k": r["k"],
                "Faelle": r["cases"],
                f"Recall@k": round(r["recall_at_k"], 4),
                "MRR": round(r["mrr"], 4),
                "Embedding": r["config"].get("embedding", {}).get("provider", ""),
            }
            for r in runs
        ],
        hide_index=True,
        width="stretch",
    )

    st.markdown("**Laeufe vergleichen**")
    selected = st.multiselect("Laeufe", runs, default=runs[:2], format_func=_run_label, key="fe_compare")
    if len(selected) < 2:
        st.caption("Mindestens zwei Laeufe waehlen.")
        return

    per_case: dict[str, dict[str, str]] = {}
    for run in selected:
        for case in run["per_case"]:
            row = per_case.setdefault(case["id"], {"Fall": case["id"], "Frage": case["query"]})
            row[f"#{run['id']} Rang"] = str(case["rank"]) if case["rank"] else "verfehlt"
    summary = {"Fall": "Summe", "Frage": ""}
    for run in selected:
        summary[f"#{run['id']} Rang"] = f"R@{run['k']}={run['recall_at_k']:.3f} MRR={run['mrr']:.3f}"
    st.dataframe([summary, *per_case.values()], hide_index=True, width="stretch")

    configs = {f"#{r['id']}": _flatten(r["config"]) for r in selected}
    keys = sorted({key for cfg in configs.values() for key in cfg})
    diff = [
        {"Parameter": key, **{run: cfg.get(key, "") for run, cfg in configs.items()}}
        for key in keys
        if len({cfg.get(key) for cfg in configs.values()}) > 1
    ]
    if diff:
        st.markdown("Unterschiede in der Config")
        st.dataframe(diff, hide_index=True, width="stretch")
    else:
        st.caption("Gleiche Config in allen gewaehlten Laeufen.")
