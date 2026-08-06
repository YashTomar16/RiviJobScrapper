from rivi.classifier import classify_title


def test_engineering_ic():
    c = classify_title("Senior Software Engineer")
    assert c.in_scope
    assert c.function == "Engineering"
    assert c.seniority_band == "IC"


def test_vp_engineering():
    c = classify_title("VP Engineering")
    assert c.in_scope
    assert c.function == "Engineering"
    assert c.seniority_band in {"VP", "SVP"}


def test_cto():
    c = classify_title("Chief Technology Officer")
    assert c.in_scope
    assert c.seniority_band == "C-level"


def test_product_manager():
    c = classify_title("Product Manager")
    assert c.in_scope
    assert c.function == "Product"
    assert c.seniority_band == "Manager"


def test_ml_engineer():
    c = classify_title("Machine Learning Engineer")
    assert c.in_scope
    assert c.function == "Machine Learning"


def test_ai_scientist():
    c = classify_title("AI Research Scientist")
    assert c.in_scope
    assert c.function in {"AI", "Machine Learning"}


def test_exclude_sales():
    c = classify_title("Account Executive")
    assert not c.in_scope


def test_exclude_product_marketing():
    c = classify_title("Product Marketing Manager")
    assert not c.in_scope


def test_exclude_hr():
    c = classify_title("HR Business Partner")
    assert not c.in_scope


def test_exclude_director_operations():
    c = classify_title("Director of Operations")
    assert not c.in_scope


def test_exclude_cfo():
    c = classify_title("Chief Financial Officer")
    assert not c.in_scope


def test_exclude_sales_engineer():
    c = classify_title("Sales Engineer")
    assert not c.in_scope


def test_head_of_data():
    c = classify_title("Head of Data Science")
    assert c.in_scope
    assert c.function == "Data"
    assert c.seniority_band == "Head"


def test_quant_developer_in_scope():
    c = classify_title("Quantitative Developer")
    # developer keyword → Engineering
    assert c.in_scope
    assert c.function == "Engineering"


def test_it_manager_in_scope():
    c = classify_title("IT Manager")
    assert c.in_scope
    assert c.function == "IT"


def test_cio_is_it():
    c = classify_title("Chief Information Officer")
    assert c.in_scope
    assert c.function == "IT"
    assert c.seniority_band == "C-level"


def test_cio_office_is_not_c_level():
    c = classify_title("Quantitative Analyst - CIO Office")
    assert c.in_scope
    assert c.function == "Data"
    assert c.seniority_band == "IC"


def test_quant_developer_cio_office_is_not_c_level():
    c = classify_title("Quantitative Developer - CIO Office")
    assert c.in_scope
    assert c.function == "Engineering"
    assert c.seniority_band == "IC"


def test_cto_standalone():
    c = classify_title("CTO")
    assert c.in_scope
    assert c.seniority_band == "C-level"


def test_office_of_the_cto_analyst_not_c_level():
    c = classify_title("Data Analyst, Office of the CTO")
    assert c.in_scope
    assert c.function == "Data"
    assert c.seniority_band == "IC"


def test_head_of_crm_technology_is_it():
    c = classify_title("Vice President, Head of CRM Technology")
    assert c.in_scope
    assert c.function == "IT"


def test_director_product_management():
    c = classify_title("Director, Product Management - Ads", "San Francisco, CA, United States")
    assert c.in_scope
    assert c.function == "Product"
    assert c.seniority_band == "Director"


def test_group_product_design_manager():
    c = classify_title("Group Product Design Manager, Rider Verticals", "San Francisco, CA")
    assert c.in_scope
    assert c.function == "Product"
    assert c.seniority_band == "Manager"


def test_solutions_architecture_manager():
    c = classify_title("Senior Manager, Solutions Architecture", "London, England")
    assert c.in_scope
    assert c.function == "Technology"
    assert c.seniority_band == "Senior Manager"


def test_software_engineering_sr_director():
    c = classify_title("Software Engineering - Sr. Director", "United States")
    assert c.in_scope
    assert c.function == "Engineering"
    assert c.seniority_band == "Senior Director"


def test_platform_management_director():
    c = classify_title("Platform Management - Director", "United States")
    assert c.in_scope
    assert c.function == "Engineering"
    assert c.seniority_band == "Director"
