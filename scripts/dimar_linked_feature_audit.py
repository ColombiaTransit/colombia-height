#!/usr/bin/env python3
"""Check actual layer schemas and small island/coast count-probes for DIMAR GIS.

Only metadata and ArcGIS returnCountOnly envelope queries are requested.
Source URLs are fixed, copied from an Experience directly linked on the
official DIMAR IDE page. These geomorphology layers are NOT certified emerged
land polygons or full-colombia coastline coverage.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from dimar_geoservice_discovery import signals, SITE_PROBES

SOURCES = {
    "acantilado": "https://ide.dimar.mil.co/serveridem/rest/services/ZONACOSTERA/Acantilado/FeatureServer/0",
    "rasgos_geomorfologicos": "https://ide.dimar.mil.co/serveridem/rest/services/ZONACOSTERA/Rasgos_geomorfologicos/FeatureServer/0",
    "unidad_geomorfologica": "https://ide.dimar.mil.co/serveridem/rest/services/ZONACOSTERA/Unidad_Geomorfológica/FeatureServer/0",
}
EXPERIENCE = "https://experience.arcgis.com/experience/7ccd7a8e14ed48f3a632200302fb26fb"
SITE_WINDOWS = {name: [round(lon-.04,5),round(lat-.04,5),round(lon+.04,5),round(lat+.04,5)]
                for name,(lon,lat) in SITE_PROBES.items()}


def request_json(session, url, params):
    r=session.get(url,params=params,timeout=(10,30))
    r.raise_for_status()
    j=r.json()
    if not isinstance(j,dict) or j.get("error"):
        raise RuntimeError(f"ArcGIS returned invalid data: {str(j)[:280]}")
    return j


def build_query(bbox):
    """Server-side intersection count; no downloaded geometry or pixel values."""
    if len(bbox)!=4 or bbox[0]>=bbox[2] or bbox[1]>=bbox[3]:
        raise ValueError("Invalid WGS84 envelope")
    return {
        "f":"json", "where":"1=1",
        "geometry":",".join(str(x) for x in bbox),
        "geometryType":"esriGeometryEnvelope", "inSR":"4326",
        "spatialRel":"esriSpatialRelIntersects",
        "returnCountOnly":"true",
    }


def inspect(session, name, url):
    if url not in SOURCES.values():
        raise ValueError("Unapproved public DIMAR linked layer URL")
    report={"layer_key":name,"layer_url":url,
            "DIMAR_linked_experience":EXPERIENCE,
            "metadata_status":"pending",
            "site_window_counts":{},"production_land_mask_verified":False}
    try:
        md=request_json(session,url,{"f":"pjson"})
        geom=md.get("geometryType")
        report.update({
            "metadata_status":"readable",
            "name":md.get("name"),"geometry_type":geom,
            "geometry_warning":signals(md.get("name") or name,geometry=geom)["classification"],
            "service_item_id":md.get("serviceItemId"),
            "copyright":str(md.get("copyrightText") or "")[:450],
            "description":str(md.get("description") or "")[:450],
            "supports_query": "Query" in str(md.get("capabilities","")),
            "fields":[{"name":f.get("name"),"type":f.get("type")}
                      for f in md.get("fields",[])[:60]],
            "extent":{"xmin":(md.get("extent") or {}).get("xmin"),
                      "ymin":(md.get("extent") or {}).get("ymin"),
                      "xmax":(md.get("extent") or {}).get("xmax"),
                      "ymax":(md.get("extent") or {}).get("ymax"),
                      "sr":(md.get("extent") or {}).get("spatialReference")},
            "no_emerged_land_polygon_inferred":True,
        })
        for site,bbox in SITE_WINDOWS.items():
            try:
                data=request_json(session,url+"/query",build_query(bbox))
                count=data.get("count")
                if not isinstance(count,int) or count<0:
                    raise ValueError("No integer feature count")
                report["site_window_counts"][site]={
                    "8km_envelope_approx_wgs84":bbox,
                    "intersecting_feature_count":count,
                    "only_geometric_window_hint_not_emerged_land_mask":True}
            except (requests.RequestException, RuntimeError, ValueError) as e:
                report["site_window_counts"][site]={
                    "8km_envelope_approx_wgs84":bbox,
                    "status":"query_unavailable", "error":str(e)[:180]}
    except (requests.RequestException,RuntimeError,ValueError) as e:
        report.update({"metadata_status":"unavailable","error":str(e)[:320]})
    return report


def run(output):
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-DIMAR-island-coast-coverage-audit/1.0",
                            "Accept":"application/json"})
    rows=[inspect(session,key,url) for key,url in SOURCES.items()]
    report={
        "status":"DIMAR_direct_linked_feature_layer_schema_and_count_audit",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "official_DIMAR_portal":"https://www.dimar.mil.co/ide",
        "linked_ArcGIS_Experience":EXPERIENCE,
        "source_layers":rows,
        "layers_inspected":len(rows),
        "metadata_readable_count":sum(x["metadata_status"]=="readable" for x in rows),
        "site_count_probe_windows":SITE_WINDOWS,
        "authoritative_emerged_land_polygon_established":False,
        "no_elevation_or_geometry_downloaded":True,
        "selected_original_COGs_unchanged":137,
        "further_COG_candidates_under_review":52,
        "national_publication_allowed":False,
        "limitations":[
            "A geomorphology Polygon need not represent dry land; a coastal Line cannot alone be rasterized as a land mask",
            "A 0-count near an island does not prove there is no land, only no feature in that layer and study window",
            "Query count features are NOT source DEM pixel coverage or legal territorial jurisdiction",
            "The DIMAR MapServer /server path was broken; this only inspects specific /serveridem links exposed publicly by the official Experience",
        ],
    }
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=Path("output/dimar-linked-feature-schema.json"))
    a=p.parse_args()
    run(a.output)


if __name__=="__main__":
    main()
