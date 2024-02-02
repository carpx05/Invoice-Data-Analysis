import streamlit as st
import fitz  # PyMuPDF
from fuzzywuzzy import fuzz, process
import pandas as pd
import re
import base64
from PyPDF2 import PdfMerger

st.header('Invoice Data Analysis')

def calculate_similarity(address1, address2):
    return fuzz.ratio(address1.lower(), address2.lower())

def preprocess_text(text):
    keywords_to_exclude = ["if undelivered, return to:", "If undelivered, return to:", "If undelivered return to:", "Customer Address"]
    text = '\n'.join(line for line in text.split('\n') if all(keyword not in line for keyword in keywords_to_exclude))
    cleaned_text = re.sub(r'[,\n]', ' ', text.lower())
    cleaned_text = ' '.join(set(cleaned_text.split()))
    return cleaned_text

def prepare_df(pdf_file, crop_down=120, crop_lr=130, crop_down_inv=50, crop_lr_inv=50):
    doc = fitz.open(pdf_file)
    df = pd.DataFrame(columns=["invoice_num", "invoice_date", "customer_address", "page_num"])

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text_instances = page.search_for("Customer Address")
        invoice_instances = page.search_for("Invoice No.")

        for text_rect in text_instances:
            x0, y0, x1, y1 = text_rect
            x0_crop = max(x0 - crop_lr, 0)
            x1_crop = min(x1 + crop_lr, page.rect.width)
            y0_crop = max(y0, 0)
            y1_crop = min(y0 + crop_down, page.rect.height)

            page.draw_rect(fitz.Rect(x0_crop, y0_crop, x1_crop, y1_crop), color=(1, 0, 0))

            cropped_area = fitz.Rect(x0_crop, y0_crop, x1_crop, y1_crop)
            cropped_text = page.get_text("text", clip=cropped_area)
            cropped_text = preprocess_text(cropped_text)

        for invoice_instance in invoice_instances:
            x0, y0, x1, y1 = invoice_instance
            x0_crop_inv = max(x0 - crop_lr_inv, 0)
            x1_crop_inv = min(x1 + crop_lr_inv, page.rect.width)
            y0_crop_inv = max(y0, 0)
            y1_crop_inv = min(y0 + crop_down_inv, page.rect.height)

            page.draw_rect(fitz.Rect(x0_crop_inv, y0_crop_inv, x1_crop_inv, y1_crop_inv), color=(1, 0, 0))

            cropped_area_inv = fitz.Rect(x0_crop_inv, y0_crop_inv, x1_crop_inv, y1_crop_inv)
            cropped_text_inv = page.get_text("text", clip=cropped_area_inv)

            invoice_num_match = re.search(r"Invoice No\.\s*(\w+)", cropped_text_inv)
            invoice_num = invoice_num_match.group(1) if invoice_num_match else None

            invoice_date_match = re.search(r"Invoice Date\s*(\d{2}.\d{2}.\d{4})", cropped_text_inv)
            invoice_date = invoice_date_match.group(1) if invoice_date_match else None
            break

        bill_instance = {"invoice_num": invoice_num, "invoice_date": invoice_date, "customer_address": cropped_text,
                         "page_num": page_num}
        df = df._append(bill_instance, ignore_index=True)
    return df

def download_link(df, filename='dataframe.csv', text='Download CSV'):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

def find_most_similar_address(query, addresses, threshold=60):
    result = process.extractOne(query, addresses)
    if result[1] >= threshold:
        return result[0]
    else:
        return None

def merge_pdfs(uploaded_files):
    merger = PdfMerger()
    for uploaded_file in uploaded_files:
        merger.append(uploaded_file, import_outline=False)
    merged_file_path = "merged_file.pdf"
    with open(merged_file_path, "wb") as output_pdf:
        merger.write(output_pdf)
    merger.close()
    return merged_file_path

def main():
    upload_option = st.selectbox("Choose upload option:", ["Single file", "Multiple files"])

    # File upload based on selected option
    if upload_option == "Single file":
        uploaded_file = st.file_uploader("Upload a single PDF file", type="pdf", accept_multiple_files=False)
    else:
        uploaded_files = st.file_uploader("Upload multiple PDF files", accept_multiple_files=True, type="pdf")
        uploaded_file = merge_pdfs(uploaded_files)
        st.success("PDFs merged successfully!")
        st.download_button(label="Download Merged PDF", data=open(uploaded_file, "rb").read(), file_name="merged_file.pdf", mime="application/pdf")


    df = prepare_df(uploaded_file)
    # pdf_file = "example.pdf"
    # crop_down = 120
    # crop_lr = 120
    # df = prepare_df(pdf_file, crop_down, crop_lr)

    if st.button('View Scanned Data'):
        st.write('You clicked the button! Here is your DataFrame:')
        st.dataframe(df)
        print("df 1 ready!")

        st.markdown(download_link(df, filename='my_dataframe.csv', text='Download CSV'), unsafe_allow_html=True)

    df['most_similar_address'] = df['customer_address'].apply(lambda x: find_most_similar_address(x, df['customer_address']))

    df_filtered = df.dropna(subset=['most_similar_address'])
    address_counts = df_filtered.groupby('most_similar_address').size().reset_index(name='count')
    result_df = pd.merge(address_counts, df[['most_similar_address', 'page_num']], on='most_similar_address', how='left')
    result_df['page_numbers'] = result_df.groupby('most_similar_address')['page_num'].transform(lambda x: ', '.join(map(str, x)))
    result_df.drop_duplicates(subset=['most_similar_address'], inplace=True)

    if st.button('View Similar Addresses'):
        st.write('You clicked the button! Here is your DataFrame:')
        st.dataframe(result_df)
        st.write('page_numbers refer to the page  number of the invoice in the merged pdf. Download Merger PDF to view.')
        print("df 2 ready!")

if __name__ == "__main__":
    main()