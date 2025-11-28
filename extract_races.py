# Standard library imports
import csv
import datetime
import re
import sys
import os

# Third-party imports
import pdfplumber


# Constants
VALID_SURFACES = ["Dirt", "Turf", "All Weather", "Tapeta"]
CSV_FIELDNAMES = ["Date", "Race #", "Surface", "Distance", "Jockey", "Trainer", "WIN", "PLACE", "SHOW"]
DATE_FORMAT_INPUT = '%B %d, %Y'
DATE_FORMAT_OUTPUT = '%Y-%m-%d'

INPUT_PATH = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "outputs")


# Parsing functions
def parse_header(text):
    """
    Parses the header to extract Track, Date, and Race number.
    Handles compressed spaces like "AQUEDUCT-January1,2025-Race1"
    
    Returns:
        tuple: (track, date_str, race_num) or (None, None, None) if not found
    """
    match = re.search(r'([A-Z\s\.]+?)\s*-\s*(.*?)\s*-\s*Race\s*(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
    return None, None, None


def parse_distance_surface(text):
    """
    Parses the distance and surface from text.
    Handles compressed spaces like "Distance:SixFurlongsOnTheDirt"
    
    Returns:
        tuple: (distance, surface) or (None, None) if not found
    """
    match = re.search(r'Distance:\s*(.*?)\s*On\s*The\s*(.*)', text, re.IGNORECASE)
    if match:
        distance = match.group(1).strip()
        surface_raw = match.group(2).strip()
        
        # Identify surface type
        surface = "Unknown"
        for vs in VALID_SURFACES:
            if vs.lower() in surface_raw.lower():
                surface = vs
                break
        
        # Clean up distance (add spaces between capitalized words)
        if " " not in distance and len(distance) > 3:
            distance = re.sub(r'(?<!^)(?=[A-Z])', ' ', distance)
             
        return distance, surface
    return None, None


def parse_trainers_footer(text):
    """
    Parses the Trainers footer section to extract trainer names by program number.
    
    Returns:
        dict: Mapping of program number (str) to trainer name (str)
    """
    trainer_map = {}
    match = re.search(r'Trainers:\s*(.*)', text, re.IGNORECASE)
    if match:
        content = match.group(1)
        entries = re.split(r'[;\n]', content)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            m = re.match(r'(\d+)\s*-\s*(.*)', entry)
            if m:
                pgm = m.group(1)
                trainer = m.group(2).strip()
                if trainer.endswith('.'):
                    trainer = trainer[:-1]
                trainer_map[pgm] = trainer
    return trainer_map


def parse_horse_row(line):
    """
    Parses a single line to extract horse data (PGM and Jockey).
    
    Args:
        line: Text line to parse
        
    Returns:
        dict: {"pgm": str, "jockey": str} or None if not a valid horse row
    """
    line = line.strip()
    if not line:
        return None
    
    parts = line.split()
    if not parts:
        return None
    
    # Find PGM: First token that is all digits
    pgm = None
    for part in parts:
        if part.isdigit():
            pgm = part
            break
    
    if not pgm:
        return None
    
    # Check for Jockey in parens
    if "(" not in line or ")" not in line:
        return None
    
    # Extract Horse and Jockey
    paren_match = re.search(r'([^\s]+)\((.*?)\)', line)
    if not paren_match:
        paren_match = re.search(r'([^\s]+)\s+\((.*?)\)', line)
    
    if not paren_match:
        return None
        
    jockey = paren_match.group(2)
    
    # Verify it's a data row by checking for Odds (decimal)
    has_odds = False
    for part in parts:
        if "." in part and part.replace('.', '').replace('*', '').isdigit():
            has_odds = True
            break
    
    if has_odds:
        return {"pgm": pgm, "jockey": jockey}
    
    return None


def format_date(date_str):
    """
    Formats date string from PDF format to YYYY-MM-DD format.
    Handles dates with or without spaces (e.g., "January 1, 2025" or "January1,2023").
    
    Args:
        date_str: Date string from PDF (e.g., "January 1, 2025" or "January1,2023")
        
    Returns:
        str: Formatted date string (YYYY-MM-DD) or original if parsing fails
    """
    try:
        # Normalize date string by adding spaces if missing
        # Pattern: "January1,2023" -> "January 1, 2023"
        normalized = re.sub(r'([a-zA-Z]+)(\d+)', r'\1 \2', date_str)  # Add space between month and day
        normalized = re.sub(r'(\d+),(\d+)', r'\1, \2', normalized)  # Add space after comma
        
        date_obj = datetime.datetime.strptime(normalized, DATE_FORMAT_INPUT)
        return date_obj.strftime(DATE_FORMAT_OUTPUT)
    except ValueError:
        return date_str  # Keep original if parsing fails


# Main extraction function
def extract_race_data(pdf_path):
    """
    Extracts race data from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        list: List of dictionaries containing race data
    """
    all_races = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text:
                continue
            
            # Parse header information
            track, date_str, race_num = parse_header(text)
            if not track:
                continue
            
            date = format_date(date_str)
            distance, surface = parse_distance_surface(text)
            trainer_map = parse_trainers_footer(text)
            
            # Collect horse rows
            horse_rows = []
            lines = text.split('\n')
            for line in lines:
                row_data = parse_horse_row(line)
                if row_data:
                    horse_rows.append(row_data)
            
            # Process collected rows (assume sorted by finish position)
            for i, row in enumerate(horse_rows):
                rank = i + 1
                win = 1 if rank == 1 else 0
                place = 1 if rank == 2 else 0
                show = 1 if rank == 3 else 0
                
                trainer = trainer_map.get(row["pgm"], "")
                
                all_races.append({
                    "Date": date,
                    "Race #": race_num,
                    "Surface": surface,
                    "Distance": distance,
                    "Jockey": row["jockey"],
                    "Trainer": trainer,
                    "WIN": win,
                    "PLACE": place,
                    "SHOW": show
                })

    return all_races


# Output functions
def save_to_csv(data, output_path):
    """
    Saves race data to a CSV file.
    
    Args:
        data: List of dictionaries containing race data
        output_path: Path to output CSV file
    """
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        writer.writerows(data)


# Main execution
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_races.py <file_digest_name>")
        sys.exit(1)
    
    
    file_digest_name = sys.argv[1]
    pdf_path = os.path.join(INPUT_PATH, file_digest_name)
    output_path = os.path.join(OUTPUT_PATH, file_digest_name.replace(".pdf", ".csv"))
    
    data = extract_race_data(pdf_path)
    save_to_csv(data, output_path)
    print(f"Extracted {len(data)} rows to {output_path}")

