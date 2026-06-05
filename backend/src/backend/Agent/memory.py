from datetime import date

"""Data structure proposal for storing numeric data:
dict[entity, dict[metric,dict[date, value]]]
Repeat for many entities, each entity with many metrics, each metric with many dates"""
raw_data: dict[Entidad,
                dict[Metricas, 
                     dict[date, float]]] = {}

calculated_data: dict[str, dict[str, dict[date, float]]] = {}

"""Function to update numeric data ...
Work in progress"""
def merge_nested(existing: dict, new:dict):
    for entity, metrics in new.items():
        if entity not in existing:
            existing[entity] = {}
            for metric, dates in metrics.items():
                if metric not in existing[entity]:
                    existing[entity][metric] = {}
                existing[entity][metric].update(dates)
    return existing