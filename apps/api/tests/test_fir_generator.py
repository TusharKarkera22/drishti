import importlib.util
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "generate_fir_data.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_fir", SPEC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tables():
    return _load().build(rows=4000)  # small for a fast test


def test_all_28_tables_present(tables):
    expected = {
        "State", "District", "UnitType", "Unit", "Rank", "Designation", "Employee",
        "CaseCategory", "GravityOffence", "CrimeHead", "CrimeSubHead", "CaseStatusMaster",
        "Court", "Act", "Section", "CrimeHeadActSection", "CasteMaster", "ReligionMaster",
        "OccupationMaster", "CaseMaster", "Inv_OccuranceTime", "ComplainantDetails",
        "Victim", "Accused", "ArrestSurrender", "ActSectionAssociation",
        "ChargesheetDetails", "inv_arrestsurrenderaccused",
    }
    assert expected.issubset(set(tables)), expected - set(tables)


def test_referential_integrity(tables):
    cm = set(tables["CaseMaster"]["CaseMasterID"])
    for child in ("Inv_OccuranceTime", "Victim", "Accused", "ComplainantDetails",
                  "ArrestSurrender", "ActSectionAssociation", "ChargesheetDetails"):
        assert set(tables[child]["CaseMasterID"]).issubset(cm), child
    assert set(tables["CaseMaster"]["GravityOffenceID"]).issubset(
        set(tables["GravityOffence"]["GravityOffenceID"]))
    assert set(tables["CaseMaster"]["CaseStatusID"]).issubset(
        set(tables["CaseStatusMaster"]["CaseStatusID"]))
    assert set(tables["CaseMaster"]["PoliceStationID"]).issubset(set(tables["Unit"]["UnitID"]))
    assert set(tables["CaseMaster"]["CaseCategoryID"]).issubset(set(tables["CaseCategory"]["CaseCategoryID"]))
    assert set(tables["CaseMaster"]["CrimeMajorHeadID"]).issubset(set(tables["CrimeHead"]["CrimeHeadID"]))
    assert set(tables["CaseMaster"]["CrimeMinorHeadID"]).issubset(set(tables["CrimeSubHead"]["CrimeSubHeadID"]))
    # 1:1 occurrence
    assert len(tables["Inv_OccuranceTime"]) == len(cm)


def test_enrichments_and_patterns(tables):
    acc = tables["Accused"]
    assert {"Phone", "Address", "UpiId"}.issubset(acc.columns)        # enrichment
    assert {"DistrictName", "StateName"}.issubset(tables["Unit"].columns)
    # ring: at least one Phone shared by >=4 accused rows
    assert (acc["Phone"].value_counts() >= 4).any()
    # mule: at least one UpiId shared across multiple cyber cases
    assert (acc["UpiId"].dropna().value_counts() >= 3).any()
