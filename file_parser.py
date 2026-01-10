import re
from docx import Document
from pypdf import PdfReader
from io import BytesIO


def parse_docx(file_bytes, return_all=False):
    """Parse DOCX file and extract tests"""
    doc = Document(BytesIO(file_bytes))
    full_text = '\n'.join([para.text for para in doc.paragraphs])
    return parse_text(full_text, return_all=return_all)


def parse_pdf(file_bytes, return_all=False):
    """Parse PDF file and extract tests"""
    pdf_reader = PdfReader(BytesIO(file_bytes))
    full_text = ''
    for page in pdf_reader.pages:
        full_text += page.extract_text() + '\n'
    return parse_text(full_text, return_all=return_all)


def parse_text(text, return_all=False):
    """Parse text content with ++++ and ==== separators"""
    tests = []
    
    # Split by ++++ to get separate tests
    test_sections = re.split(r'\+\+\+\+', text)
    
    for section in test_sections:
        section = section.strip()
        if not section:
            continue
        
        questions = []
        # Split by lines to find questions
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        
        current_question = None
        current_answers = []
        # Use actual question number from file instead of auto-incrementing
        question_number = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check if this is a question (starts with number and dot)
            question_match = re.match(r'^(\d+)\.\s*(.+)$', line)
            if question_match:
                # Save previous question if exists
                if current_question and question_number is not None:
                    questions.append({
                        'question_number': question_number,
                        'question_text': current_question,
                        'answers': current_answers
                    })
                
                # Start new question - use actual number from file
                question_number = int(question_match.group(1))  # Use actual number from file
                current_question = question_match.group(2).strip()
                current_answers = []
                i += 1
                
                # Look for answers after the question
                while i < len(lines) and lines[i].startswith('===='):
                    i += 1
                    if i < len(lines):
                        answer_line = lines[i]
                        is_correct = answer_line.startswith('#')
                        if is_correct:
                            answer_text = answer_line[1:].strip()
                        else:
                            answer_text = answer_line.strip()
                        
                        if answer_text:
                            current_answers.append({
                                'text': answer_text,
                                'is_correct': is_correct
                            })
                        i += 1
                
                continue
            
            # Check if this is an answer separator
            if line.startswith('===='):
                i += 1
                if i < len(lines):
                    answer_line = lines[i]
                    is_correct = answer_line.startswith('#')
                    if is_correct:
                        answer_text = answer_line[1:].strip()
                    else:
                        answer_text = answer_line.strip()
                    
                    if answer_text and current_question:
                        current_answers.append({
                            'text': answer_text,
                            'is_correct': is_correct
                        })
                    i += 1
                continue
            
            i += 1
        
        # Save last question
        if current_question and question_number is not None:
            questions.append({
                'question_number': question_number,
                'question_text': current_question,
                'answers': current_answers
            })
        
        if questions:
            tests.append({
                'questions': questions
            })
    
    if return_all:
        return tests  # Return all tests
    return tests[0] if tests else None  # Return first test or None for backward compatibility


def validate_parsed_test(parsed_test):
    """Validate that parsed test has valid structure"""
    if not parsed_test or 'questions' not in parsed_test:
        return False, "Test formati noto'g'ri. Test savollar topilmadi."
    
    questions = parsed_test['questions']
    if len(questions) == 0:
        return False, "Testda savollar topilmadi."
    
    for i, q in enumerate(questions, 1):
        if not q.get('question_text'):
            return False, f"{i}-savol matni topilmadi."
        
        answers = q.get('answers', [])
        if len(answers) < 2:
            return False, f"{i}-savol uchun kamida 2 ta javob kerak."
        
        correct_count = sum(1 for a in answers if a.get('is_correct'))
        if correct_count != 1:
            return False, f"{i}-savol uchun bitta to'g'ri javob belgilanishi kerak (# belgisi bilan)."
    
    return True, "Test muvaffaqiyatli yuklandi!"
