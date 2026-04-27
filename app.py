import streamlit as st
import requests
import pandas as pd
from collections import defaultdict
import time
import os
from io import BytesIO

st.set_page_config(page_title="Shopify Bulk Price Updater", layout="wide")

st.title("🛍️ Shopify Bulk Variant Price Updater")

# -----------------------------
# USER INPUTS
# -----------------------------
shop_domain = st.text_input("Shopify Store Domain", placeholder="your-store.myshopify.com")
shop_token = st.text_input("Admin API Access Token", type="password")

SHOP_TOKEN = os.getenv("SHOP_TOKEN")
SHOP_DOMAIN = os.getenv("SHOP_DOMAIN")


if shop_domain.lower() == "sushain.in" or shop_domain.lower() == "sushain":
    # shop_domain= "gggzi3-qd.myshopify.com"
    shop_domain= SHOP_DOMAIN

if shop_token == "1212":
    shop_token = SHOP_TOKEN

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

run_button = st.button("🚀 Start Update")

log_data = []

# -----------------------------
# HELPERS
# -----------------------------
def log(message, status="INFO"):
    log_entry = {
        "message": message,
        "status": status
    }
    log_data.append(log_entry)
    st.write(f"[{status}] {message}")


def read_excel(file):
    df = pd.read_excel(file)
    df = df.fillna("")
    return df.to_dict(orient="records")


def fetch_variants_by_skus(skus, shop_url, headers):
    query = """
    query ($query: String!) {
      productVariants(first: 250, query: $query) {
        edges {
          node {
            id
            sku
            product {
              id
            }
          }
        }
      }
    }
    """

    search_query = " OR ".join([f"sku:{sku}" for sku in skus])

    response = requests.post(
        shop_url,
        headers=headers,
        json={"query": query, "variables": {"query": search_query}},
    )

    data = response.json()

    variant_map = {}
    for edge in data.get("data", {}).get("productVariants", {}).get("edges", []):
        node = edge["node"]
        variant_map[node["sku"]] = {
            "variant_id": node["id"],
            "product_id": node["product"]["id"]
        }

    return variant_map


def bulk_update(grouped_variants, shop_url, headers):
    mutation = """
    mutation updateVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    for product_id, variants in grouped_variants.items():
        variables = {
            "productId": product_id,
            "variants": variants
        }

        response = requests.post(
            shop_url,
            headers=headers,
            json={"query": mutation, "variables": variables},
        )

        result = response.json()
        errors = result.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors")

        if errors:
            log(f"Errors for product {product_id}: {errors}", "ERROR")
        else:
            log(f"Updated {len(variants)} variants for product {product_id}", "SUCCESS")

        time.sleep(0.5)


def process(file):
    shop_url = f"https://{shop_domain}/admin/api/2024-01/graphql"

    headers = {
        "X-Shopify-Access-Token": shop_token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    records = read_excel(file)

    BATCH_SIZE = 50
    all_grouped = defaultdict(list)

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        skus = [row["sku"] for row in batch]

        variant_map = fetch_variants_by_skus(skus, shop_url, headers)

        for row in batch:
            sku = row["sku"]
            price = row["price"]
            compare_price = row["compare_at_price"]

            if sku not in variant_map:
                log(f"SKU not found: {sku}", "ERROR")
                continue

            variant_info = variant_map[sku]

            variant_input = {
                "id": variant_info["variant_id"],
                "price": str(price),
                "compareAtPrice": str(compare_price) if compare_price else None
            }

            all_grouped[variant_info["product_id"]].append(variant_input)

        log(f"Processed batch {i // BATCH_SIZE + 1}")

    bulk_update(all_grouped, shop_url, headers)


def generate_log_excel():
    df = pd.DataFrame(log_data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output


# -----------------------------
# RUN APP
# -----------------------------
if run_button:
    if not shop_domain or not shop_token or not uploaded_file:
        st.error("Please provide all inputs")
    else:
        log("Starting process...", "INFO")
        process(uploaded_file)
        log("Process completed", "DONE")

        st.success("✅ Finished")

        excel_file = generate_log_excel()

        st.download_button(
            label="📥 Download Logs",
            data=excel_file,
            file_name="update_logs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )