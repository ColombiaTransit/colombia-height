#!/usr/bin/env python3
"""Read-only ArcGIS Hub/Online DIMAR coastal dataset provenance discovery.

Official DIMAR portal links to the public Hub at HUB_URL. Search results
ARE NOT official merely because 'DIMAR' occurs in tags or titles. Confirm
ArcGIS organization by an exact ArcGIS Hub Site Application URL match,
otherwise retain every item as unverified. No polygon downloaded or source
manifest modified; this is a fail-closed catalogue inventory.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from dimar_geoservice_discovery import (
    PORTAL, MARINE, INCLUDE, load_study_candidates, normalize, signals,
)

HUB_URL = "https://datos-abiertos-dimar.hub.arcgis.com"
OFFICIAL_LINKED_EXPERIENCE_ID = "7ccd7a8e14ed48f3a632200302fb26fb"
EXPERIENCE_ITEM_API = "https://www.arcgis.com/sharing/rest/content/items/" + OFFICIAL_LINKED_EXPERIENCE_ID
SEARCH = "https://www.arcgis.com/sharing/rest/search"
QUERIES = (
    '"datos-abiertos-dimar"',
    'title:"Datos Abiertos IDE"',
    'DIMAR AND costa',
    'DIMAR AND litoral',
    'DIMAR AND isla',
    'DIMAR AND geomorfologia',
    '"Línea de Costa" AND Colombia',
    '"Malpelo" AND DIMAR',
)


def standardize_url(url):
    url = str(url or "").strip().rstrip("/")
    p = urlsplit(url)
    return (p.scheme.lower(), (p.hostname or "").lower(), p.path.lower().rstrip("/"))


def portal_identity_from_items(items):
    """Require an exact Hub hostname match; arbitrary DIMAR tags are insufficient."""
    official = standardize_url(HUB_URL)
    verified = []
    for item in items:
        item_url = standardize_url(item.get("url"))
        if item_url != official:
            continue
        if item.get("type") not in ("Hub Site Application", "Site Application"):
            continue
        org_id = item.get("orgId")
        if not isinstance(org_id, str) or not org_id:
            continue
        verified.append({"org_id": org_id, "item_id": item.get("id"),
                         "owner": item.get("owner"), "url": item.get("url")})
    orgs = {x["org_id"] for x in verified}
    if len(orgs) > 1:
        raise RuntimeError("Conflicting ArcGIS organization IDs for the exact DIMAR Hub URL")
    return verified


def experience_identity(session):
    """Official DIMAR website explicitly links this Experience item ID.

    If public ArcGIS metadata confirms exactly the same item ID, its orgId
    is a verified portal-linked publisher *lead*, not a land-mask licence.
    """
    r = session.get(EXPERIENCE_ITEM_API, params={"f": "json"}, timeout=(10, 35))
    r.raise_for_status()
    item = r.json()
    if not isinstance(item, dict) or item.get("id") != OFFICIAL_LINKED_EXPERIENCE_ID:
        raise ValueError("DIMAR-linked ArcGIS Experience item identity mismatch")
    org = item.get("orgId")
    if not isinstance(org, str) or not org:
        raise ValueError("DIMAR-linked Experience item lacks ArcGIS orgId")
    return [{"org_id": org, "item_id": OFFICIAL_LINKED_EXPERIENCE_ID,
             "owner": item.get("owner"),
             "url": item.get("url"),
             "proof": "item_id_from_official_DIMAR_ide_page"}]


def read_search(session, q, num=80):
    r = session.get(SEARCH, params={"f":"json","q":q,"num":num,"start":1},
                    timeout=(10,35), headers={"Accept":"application/json"})
    r.raise_for_status()
    j = r.json()
    if not isinstance(j,dict) or j.get("error"):
        raise ValueError(f"ArcGIS item search error for {q}: {str(j)[:250]}")
    results = j.get("results")
    if not isinstance(results,list):
        raise ValueError("No item search results key")
    return results, j.get("total",len(results))


def shortlist(items, identity, verified_label="ARCGIS_ORG_MATCH_TO_OFFICIAL_DIMAR_HUB_SITE"):
    """Every result retains its provenance class and unapproved status."""
    orgs = {x["org_id"] for x in identity}
    results=[]
    seen=set()
    for item in items:
        id=item.get("id")
        if not id or id in seen:
            continue
        seen.add(id)
        title=item.get("title") or ""
        text=" ".join((title, item.get("description") or "", item.get("snippet") or "",
                       " ".join(str(a) for a in (item.get("tags") or []))))
        title_norm=normalize(title)
        context_norm=normalize(text)
        coastal=signals(title)
        # Do not retain every "DIMAR" item. It must have coast/island signals.
        if not (coastal["coastline_relevant"] or
                any(k in context_norm for k in INCLUDE) and any(k in title_norm for k in
                       ("litoral", "zona", "geografia", "costa", "isla", "playa"))):
            continue
        if item.get("orgId") in orgs:
            provenance=verified_label
        else:
            provenance="ARCGIS_SEARCH_ONLY_PUBLISHER_UNVERIFIED"
        results.append({
            "item_id":id, "title":title, "type":item.get("type"),
            "url":item.get("url"), "owner":item.get("owner"),
            "org_id":item.get("orgId"), "access":item.get("access"),
            "modified":item.get("modified"), "license_info":str(item.get("licenseInfo") or "")[:300],
            "tags":item.get("tags",[])[:20],
            "provenance":provenance,
            "possibly_marine_not_emerged_land":any(s in title_norm for s in MARINE),
            "land_mask_status":"NOT_VERIFIED_NO_GEOMETRY",
        })
    return sorted(results,key=lambda x:(x["provenance"].endswith("UNVERIFIED"),
                                       normalize(x["title"])))


def run(output):
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-DIMAR-Hub-discovery/1.0"})
    results=[]
    queries=[]
    errors=[]
    for q in QUERIES:
        try:
            items,total=read_search(session,q)
            results.extend(items)
            queries.append({"query":q,"total":total,"retrieved":len(items)})
        except (requests.RequestException, ValueError) as e:
            errors.append({"query":q,"error":str(e)[:320]})
    # Derive official organization only from a link-matched public Hub Site
    # item, *never* from an unrelated DIMAR keyword.
    hub_identity=portal_identity_from_items(results)
    app_identity=[]
    try:
        app_identity=experience_identity(session)
    except (requests.RequestException,ValueError) as e:
        errors.append({"proof":"linked_official_DIMAR_Experience",
                       "error":str(e)[:320]})
    if hub_identity and app_identity and hub_identity[0]["org_id"]!=app_identity[0]["org_id"]:
        raise RuntimeError("DIMAR portal Hub and Experience item organization IDs disagree")
    identity=hub_identity or app_identity
    evidence_type="exact_hub_site_url" if hub_identity else (
        "official_DIMAR_page_linked_Experience_item" if app_identity else "not_verified")
    if identity:
        org=identity[0]["org_id"]
        for q in (f"orgid:{org} AND (costa OR litoral OR isla)",
                  f"orgid:{org} AND (linea OR geomorfologia OR poligono)",
                  f"orgid:{org} AND type:\"Feature Service\"",
                  f"orgid:{org} AND type:\"Map Service\""):
            try:
                items,total=read_search(session,q)
                results.extend(items)
                queries.append({"query":q,"total":total,"retrieved":len(items)})
            except (requests.RequestException,ValueError) as e:
                errors.append({"query":q,"error":str(e)[:320]})
    relevant=shortlist(results,identity,
        verified_label=("ARCGIS_ORG_MATCH_TO_OFFICIAL_DIMAR_PORTAL_LINKED_EXPERIENCE"
                        if evidence_type=="official_DIMAR_page_linked_Experience_item"
                        else "ARCGIS_ORG_MATCH_TO_OFFICIAL_DIMAR_HUB_SITE"))
    candidates=load_study_candidates(
        Path("data/official-igac-source-review-2026-11-13.json"))
    report={
        "status":"public_ArcGIS_Hub_dataset_search_no_land_mask_validated",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "dimar_official_portal":PORTAL,
        "official_portal_links_to_hub":HUB_URL,
        "public_search_api":SEARCH,
        "queries":queries,"errors":errors,
        "exact_official_hub_site_item_matches":hub_identity,
        "official_DIMAR_portal_linked_experience_item_matches":app_identity,
        "publisher_organization_evidence_type":evidence_type,
        "arcgis_item_org_verified_by_exact_hub_match":bool(hub_identity),
        "arcgis_org_verification_via_official_linked_experience":bool(app_identity),
        "coastal_or_island_search_items":relevant,
        "items_total":len(relevant),
        "provenance_counts":dict(Counter(x["provenance"] for x in relevant)),
        "source_cog_candidates_unmodified":len(candidates),
        "selected_original_source_cogs_still":137,
        "coastline_polygon_accepted":False,
        "national_publication_allowed":False,
        "limitations":[
            "A public ArcGIS search hit is NOT an official DIMAR dataset",
            "Hub item association requires exact Hub Site Application URL and matching ArcGIS organization",
            "Search descriptions are metadata and DO NOT prove geometry type or land/sea semantics",
            "Copyright, datum, coverage and licence must be verified in individual data layers",
            "No public search result is promoted to a territorial land mask",
            "This report cannot exclude offshore islands such as Malpelo based on missing metadata",
        ],
    }
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in
                      ("coastal_or_island_search_items",)},
                     ensure_ascii=False,indent=2),flush=True)
    for x in relevant[:55]:
        print(x["provenance"],x["type"],x["title"],str(x.get("url") or "")[:160],flush=True)
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,default=Path("output/dimar-hub/dimar-hub-search.json"))
    args=ap.parse_args()
    run(args.output)


if __name__=="__main__":
    main()
