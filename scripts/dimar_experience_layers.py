#!/usr/bin/env python3
"""Inspect a DIMAR-linked public ArcGIS Experience configuration and webmap.

The specific Experience URL is linked on DIMAR's official IDE page.
Use only ArcGIS Public REST metadata and data references; no exports,
credentials, geofeatures, DEM source changes, or ocean inference.
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dimar_geoservice_discovery import signals, normalize

EXPERIENCE_ID="7ccd7a8e14ed48f3a632200302fb26fb"
EXPERIENCE_LINK="https://experience.arcgis.com/experience/"+EXPERIENCE_ID
DIMAR_REFERENCE="https://www.dimar.mil.co/ide"
ARCGIS="https://www.arcgis.com/sharing/rest/content/items"
HEX_ID=re.compile(r"^[0-9a-fA-F]{32}$")
SERVICE_PATH=re.compile(r"/(?:FeatureServer|MapServer)(?:/\d+)?(?:/)?$",re.I)


def public_arcgis_url(url):
    """Do not follow private/local URLs embedded in untrusted app JSON."""
    parts=urlsplit(str(url))
    host=(parts.hostname or "").lower()
    return parts.scheme=="https" and (host=="arcgis.com" or host.endswith(".arcgis.com")
          or host=="ide.dimar.mil.co" or host=="mapas2.igac.gov.co")


def service_reference(url):
    """No query, credentials, fragments or arbitrary path to be re-requested."""
    if not public_arcgis_url(url):
        return None
    parts=urlsplit(str(url))
    if parts.username or parts.password or not SERVICE_PATH.search(parts.path):
        return None
    if parts.query or parts.fragment:
        return None
    return str(url).rstrip("/")


def crawl_refs(obj):
    """Extract only recognized item-id keys and public ArcGIS service URLs."""
    item_ids=set()
    service_urls=set()
    def walk(v, key="", depth=0):
        if depth>35:
            return
        if isinstance(v,dict):
            for k,value in v.items():
                walk(value,str(k).lower(),depth+1)
        elif isinstance(v,list):
            for x in v[:500]:
                walk(x,key,depth+1)
        elif isinstance(v,str):
            if key in ("itemid","webmapid","portalitemid","webmap","item_id") and HEX_ID.fullmatch(v):
                item_ids.add(v.lower())
            u=service_reference(v)
            if u:
                service_urls.add(u)
    walk(obj)
    return sorted(item_ids),sorted(service_urls)


def safe_json(session,url,params=None):
    r=session.get(url,params={"f":"json",**(params or {})},timeout=(10,30))
    r.raise_for_status()
    if len(r.content)>12_000_000:
        raise ValueError("Public ArcGIS item larger than capped 12MB")
    j=r.json()
    if not isinstance(j,(dict,list)) or (isinstance(j,dict) and j.get("error")):
        raise ValueError(f"Invalid public ArcGIS item {url}: {str(j)[:180]}")
    return j


def inspect_experience(session):
    item=safe_json(session,f"{ARCGIS}/{EXPERIENCE_ID}")
    if item.get("id")!=EXPERIENCE_ID:
        raise RuntimeError("Experience item ID mismatch")
    try:
        config=safe_json(session,f"{ARCGIS}/{EXPERIENCE_ID}/data")
    except (requests.RequestException, ValueError) as e:
        return item,None,[{"url":f"{ARCGIS}/{EXPERIENCE_ID}/data","error":str(e)[:250]}]
    return item,config,[]


def examine_service_metadata(session,urls,limit=25):
    results=[]
    failures=[]
    for url in urls[:limit]:
        if not service_reference(url):
            continue
        try:
            info=safe_json(session,url)
            children=info.get("layers") or []
            layers=[{"name":x.get("name"),"id":x.get("id"),
                     "metadata_only_not_land_mask":True} for x in children[:40]]
            results.append({"url":url,
                "name":info.get("serviceDescription") or info.get("mapName") or "",
                "capabilities":info.get("capabilities"),
                "license_or_attribution":str(info.get("copyrightText") or "")[:300],
                "layers":layers, "geomorphology_layer_metadata_only":True})
        except (requests.RequestException,ValueError) as e:
            failures.append({"url":url,"error":str(e)[:280]})
    return results,failures


def run(output):
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-DIMAR-experience-research/1.0",
                            "Accept":"application/json"})
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    item,config,errors=inspect_experience(session)
    ids,services=crawl_refs(config) if config is not None else ([],[])
    # WebMap child config often has operational layer references that an
    # ArcGIS Experience wrapper only expresses as a web map itemId.
    children=[]
    layer_urls=set(services)
    for webmap_id in ids[:22]:
        try:
            item_meta=safe_json(session,f"{ARCGIS}/{webmap_id}")
            subtype=item_meta.get("type")
            children.append({"id":webmap_id,"title":item_meta.get("title"),
                             "type":subtype,"orgId":item_meta.get("orgId"),
                             "owner":item_meta.get("owner")})
            if subtype == "Web Map":
                map_data=safe_json(session,f"{ARCGIS}/{webmap_id}/data")
                _,new_urls=crawl_refs(map_data)
                layer_urls.update(new_urls)
        except (requests.RequestException,ValueError) as e:
            errors.append({"item_id":webmap_id,"error":str(e)[:250]})
    metadata,errs=examine_service_metadata(session,sorted(layer_urls))
    errors.extend(errs)
    report={
        "status":"official_DIMAR_linked_ArcGIS_experience_metadata_probe",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "official_DIMAR_page":DIMAR_REFERENCE,
        "DIMAR_linked_Experience_URL":EXPERIENCE_LINK,
        "published_ArcGIS_item_id":EXPERIENCE_ID,
        "published_ArcGIS_item_title":item.get("title"),
        "publisher_ArcGIS_orgId_unverified":item.get("orgId"),
        "publisher_owner_unverified":item.get("owner"),
        "experience_config_readable":config is not None,
        "referenced_item_ids":ids,
        "child_public_item_metadata":children,
        "public_feature_and_map_services_found":sorted(layer_urls),
        "public_service_metadata":metadata,
        "metadata_errors":errors[:45],
        "available_verified_emerged_land_polygon":False,
        "shoreline_lines_are_not_land_polygons":True,
        "no_degrees_covered_inferred_from_a_line":True,
        "original_copernicus_selected_cogs":137,
        "additional_candidate_cogs_reviewed_count":52,
        "quitasueno_excluded":True,
        "national_publication_allowed":False,
        "interpretation":"These are public map/app references linked by DIMAR; not automatically an approved high-resolution coastal land/sea mask.",
    }
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in
                      ("child_public_item_metadata","public_service_metadata","metadata_errors")},
                     ensure_ascii=False,indent=2),flush=True)
    for record in metadata:
        print("MAP_SERVICE",record["url"],
              "LAYERS",",".join(str(x["name"]) for x in record["layers"][:16]),flush=True)
    for e in errors[:15]:
        print("EXPERIENCE_WARNING",json.dumps(e),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=Path("output/dimar-experience/dimar-experience-report.json"))
    args=p.parse_args()
    run(args.output)


if __name__=="__main__":
    main()
