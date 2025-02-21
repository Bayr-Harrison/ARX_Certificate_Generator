import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import io
import zipfile
from datetime import datetime
from supabase import create_client
import requests
import os

# Load secrets for Supabase
SUPABASE_URL = "https://yetmtzyyztirghaxnccp.supabase.co"
SUPABASE_DB_NAME = st.secrets["SUPABASE_DB_NAME"]
SUPABASE_USER = st.secrets["SUPABASE_USER"]
SUPABASE_PASSWORD = st.secrets["SUPABASE_PASSWORD"]
SUPABASE_HOST = st.secrets["SUPABASE_HOST"]
SUPABASE_PORT = st.secrets["SUPABASE_PORT"]

supabase = create_client(SUPABASE_URL, st.secrets["SUPABASE_PASSWORD"])

# Certificate template mapping
TEMPLATE_MAP = {
    "Employee of the Month": "001.pdf",
    "Student of the Month": "002.pdf"
}

# Streamlit UI
st.set_page_config(page_title="Certificate Generator", layout="wide")
tabs = st.tabs(["Certificate Generator", "Certificate Log"])

with tabs[0]:  # Certificate Generator Page
    st.title("Certificate Generator")
    cert_type = st.selectbox("Select Certificate Type", list(TEMPLATE_MAP.keys()))
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file and st.button("Generate Certificates"):
        df = pd.read_csv(uploaded_file)
        zip_buffer = io.BytesIO()
        zipf = zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED)
        
        cert_links = []
        
        for index, row in df.iterrows():
            iatc_id = row['iatc_id']
            name = row['name']
            issue_date = datetime.strptime(row['issue_date'], "%d/%m/%Y").strftime("%Y-%m-%d")
            template_path = f"{SUPABASE_URL}/storage/v1/object/public/certificates/templates/{TEMPLATE_MAP[cert_type]}"
            file_name = f"{iatc_id}_{TEMPLATE_MAP[cert_type][:3]}_{issue_date}.pdf"
            cert_url = f"{SUPABASE_URL}/storage/v1/object/public/certificates/issued_certificates/{file_name}"
            
            # Load template
            response = requests.get(template_path)
            doc = fitz.open(stream=response.content, filetype="pdf")
            page = doc[0]
            
            # Add text to certificate
            text_font = "helv"
            text_size = 40
            
            page.insert_text((200, 300), name, fontsize=text_size, fontname=text_font)
            page.insert_text((200, 350), iatc_id, fontsize=text_size, fontname=text_font)
            page.insert_text((200, 400), issue_date, fontsize=text_size, fontname=text_font)
            
            pdf_buffer = io.BytesIO()
            doc.save(pdf_buffer)
            pdf_buffer.seek(0)
            
            # Upload certificate to Supabase
            upload_url = f"{SUPABASE_URL}/storage/v1/object/public/certificates/issued_certificates/{file_name}"
            headers = {"Authorization": f"Bearer {st.secrets['SUPABASE_PASSWORD']}", "Content-Type": "application/pdf"}
            requests.put(upload_url, data=pdf_buffer.getvalue(), headers=headers)
            
            # Save to zip file
            zipf.writestr(file_name, pdf_buffer.getvalue())
            
            # Append to Supabase database
            data = {"iatc_id": iatc_id, "name": name, "issue_date": issue_date, "cert_type": cert_type, "cert_url": cert_url}
            supabase.table("certificates").insert(data).execute()
            
            cert_links.append(cert_url)
        
        zipf.close()
        zip_buffer.seek(0)
        st.download_button("Download Certificates (ZIP)", zip_buffer, file_name="certificates.zip", mime="application/zip")
        
        st.success("Certificates generated and uploaded successfully!")

with tabs[1]:  # Certificate Log Page
    st.title("Certificate Log")
    query = supabase.table("certificates").select("*").execute()
    df_log = pd.DataFrame(query.data)
    st.dataframe(df_log)
