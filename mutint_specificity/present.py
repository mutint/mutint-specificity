"""evospec's answer, arranged for the page and the CSV downloads.

evospec returns dicts keyed by treatment, which a Django template cannot index by a variable;
this lines every per-treatment value up in the order of the page's columns, and formats the
numbers once, here, so the page and the downloads cannot write them differently.
"""


def number(value, digits=3):
    if value is None:
        return "–"
    if isinstance(value, int):
        return str(value)
    return ("%." + str(digits) + "f") % value


def p_value(value, permutations=None):
    """A p-value as a person reads one: three significant figures, scientific when small.

    A randomization p of 0 means none of the randomizations reached the observed statistic,
    which is "less than one in however many were run" and not zero.
    """
    if value is None:
        return "–"
    if value == 0 and permutations:
        return "< %s" % _general(1.0 / permutations)
    return _general(value)


def _general(value):
    if value == 0:
        return "0"
    if value < 0.001:
        return "%.2e" % value
    return "%.3g" % value


def _dice(dice):
    if dice is None:
        return None
    rows = []
    for index, comparison in enumerate(dice["comparisons"]):
        threshold = dice["alpha"] if index == 0 else dice.get("bonferroni_alpha", dice["alpha"])
        p = comparison["p_value"]
        rows.append({
            "comparison": comparison["comparison"],
            "grand": index == 0,
            "within": number(comparison["within"]),
            "between": number(comparison["between"]),
            "mean": number(comparison["mean"]),
            "at_least": comparison["randomized_at_least"],
            "p": p_value(p, dice["permutations"]),
            "significant": p is not None and p <= threshold,
        })
    return {
        "skipped": dice["skipped"],
        "permutations": dice["permutations"],
        "excluded_genes": dice["excluded_genes"],
        "alpha": dice["alpha"],
        "pairwise_comparisons": dice.get("pairwise_comparisons", 0),
        "bonferroni_alpha": _general(dice.get("bonferroni_alpha", dice["alpha"])),
        "rows": rows,
    }


def _genes(genes, treatments):
    rows = []
    for row in genes["rows"]:
        rows.append({
            "gene": row["gene"],
            "genomes": [row["genomes"].get(t, 0) for t in treatments],
            "total_genomes": row["total_genomes"],
            "total_mutations": row["total_mutations"],
            "most_hit_treatment": row["most_hit_treatment"] or "",
            "p": p_value(row["p_value"]),
            "significant": row["significant"],
            "significant_bonferroni": row["significant_bonferroni"],
        })
    # A gene with one mutation is listed and never tested, and in a real experiment most genes
    # are that: the TEE example has 21 genes tested and 70 hit once. The page folds them away
    # beneath the table rather than making the tested ones a screen's scroll from each other.
    return {
        "rows": [r for r in rows if r["total_mutations"] > 1],
        "once": [r for r in rows if r["total_mutations"] <= 1],
        "genes_tested": genes["genes_tested"],
        "alpha": genes["alpha"],
        "bonferroni_alpha": _general(genes["bonferroni_alpha"]),
        "significant": sum(1 for r in rows if r["significant"]),
    }


def _mw(test):
    test = test or {}
    return [p_value(test.get(k)) for k in ("less", "greater", "two_sided")]


def _counts(counts, samples, experiment_id):
    def summary(row):
        return {"treatment": row["treatment"], "genomes": row["genomes"],
                "total": row["total"], "valid": row["valid"],
                "mean_total": number(row["mean_total"], 2),
                "mean_valid": number(row["mean_valid"], 2)}

    summaries = [summary(r) for r in counts["per_treatment"]]
    footer = [summary(counts["overall"])]
    if counts["excluding_control"]:
        footer.append(summary(counts["excluding_control"]))
    tests = {}
    for kind in ("total", "valid"):
        t = counts["tests"][kind]
        tests[kind] = {
            "minimum": t["minimum"], "minimum_genomes": ", ".join(t["minimum_genomes"]),
            "maximum": t["maximum"], "maximum_genomes": ", ".join(t["maximum_genomes"]),
            "vs_rest": [{"treatment": e["treatment"], "p": _mw(e["mann_whitney"])}
                        for e in t["vs_rest"]],
            "kruskal_wallis": p_value(t["kruskal_wallis"]),
            "vs_control": [{"treatment": e["treatment"], "p": _mw(e["mann_whitney"])}
                           for e in (t["vs_control"] or [])],
            "kruskal_wallis_excluding_control": p_value(t["kruskal_wallis_excluding_control"]),
        }
    return {
        "control": counts["control"],
        "summaries": summaries,
        "footer": footer,
        "per_genome": [dict(r, url=_sample_url(samples.get(r["genome"]), experiment_id))
                       for r in counts["per_genome"]],
        "tests": tests,
    }


def _sample_url(sample_id, experiment_id):
    if sample_id is None:
        return ""
    return "/mutations/breseq?experiment_id=%d&sample_id=%d" % (experiment_id, sample_id)


def _types(types):
    families = types["mob_families"]

    def row(entry):
        t = entry["types"]
        return {"treatment": entry["treatment"],
                "cells": [t["SNP"], entry["synonymous"], entry["nonsynonymous"], t["DEL"],
                          t["AMP"], t["INS"], t["SUB"], t["INV"], t["CON"], t["MOB"]]
                + [entry["mob_families"].get(f, 0) for f in families]}

    return {
        "families": families,
        "rows": [row(e) for e in types["per_treatment"]],
        "total": row(types["total"]),
        "deletion_lengths": types["deletion_lengths"],
        "amplification_lengths": types["amplification_lengths"],
        "amp_del": types["amp_del"],
    }


def present(result, experiment_id):
    """Everything the results section of the page draws."""
    treatments = result["treatments"]
    samples = result.get("samples") or {}
    per_treatment = {r["treatment"]: r for r in result["counts"]["per_treatment"]}
    return {
        "treatments": treatments,
        "genomes": len(result["genomes"]),
        "genomes_per_treatment": [{"treatment": t, "genomes": per_treatment[t]["genomes"]}
                                  for t in treatments],
        "left_out": [dict(entry, url=_sample_url(entry["sample_id"], experiment_id))
                     for entry in result.get("left_out") or []],
        "dice": _dice(result["dice"]),
        "dice_excluding_significant": _dice(result["dice_excluding_significant"]),
        "genes": _genes(result["genes"], treatments),
        "counts": _counts(result["counts"], samples, experiment_id),
        "types": _types(result["types"]),
    }


def gene_table_rows(result):
    """The Genes table as CSV rows: a header, then one row per gene."""
    treatments = result["treatments"]
    yield (["gene"] + ["genomes: %s" % t for t in treatments]
           + ["mutations: %s" % t for t in treatments]
           + ["total genomes", "total mutations", "most hit treatment", "p-value",
              "significant", "significant (Bonferroni)"])
    for row in result["genes"]["rows"]:
        yield ([row["gene"]] + [row["genomes"].get(t, 0) for t in treatments]
               + [row["mutations"].get(t, 0) for t in treatments]
               + [row["total_genomes"], row["total_mutations"],
                  row["most_hit_treatment"] or "",
                  "" if row["p_value"] is None else repr(row["p_value"]),
                  int(row["significant"]), int(row["significant_bonferroni"])])


def matrix_rows(result):
    """Genes by genomes, each cell the number of that genome's mutations in that gene --
    evospec's `-m` file, with a second header row naming each genome's treatment."""
    genomes = result["genomes"]
    names = [g["name"] for g in genomes]
    yield ["gene"] + names
    yield ["treatment"] + [g["treatment"] for g in genomes]
    counts = {}
    for row in result["genes"]["rows"]:
        counts[row["gene"]] = [0] * len(genomes)
    # `genomes[i]["genes"]` is the set; the per-mutation count is not in the stored result,
    # so the matrix counts genomes hit (0/1), which is what the analysis itself uses.
    for index, genome in enumerate(genomes):
        for gene in genome["genes"]:
            if gene in counts:
                counts[gene][index] = 1
    for row in result["genes"]["rows"]:
        yield [row["gene"]] + counts[row["gene"]]
