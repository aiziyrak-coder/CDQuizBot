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


def is_correct_answer_marker(text):
    """Check if text starts with a correct answer marker"""
    markers = ['#', '*', '✓', '√', '+', '→', '→→', '>>', '✅', '✔']
    text_stripped = text.strip()
    for marker in markers:
        if text_stripped.startswith(marker):
            return True, text_stripped[len(marker):].strip()
    return False, text_stripped


def is_answer_option(line):
    """Check if line is an answer option (a), b), c), d) or a. b. c. d.)"""
    # Match patterns like: a), b), c), d) or a. b. c. d. or A) B) C) D)
    pattern = r'^([a-zA-Z])[\.\)]\s*(.+)$'
    match = re.match(pattern, line)
    if match:
        return True, match.group(1).lower(), match.group(2).strip()
    return False, None, None


def parse_text(text, return_all=False):
    """
    Parse text content with flexible format support:
    1. Format with ++++ and ==== separators
    2. Format with ++++ but no question numbers
    3. Format without separators, just questions and answers (a), b), c), d))
    """
    tests = []
    
    # Check if text contains ++++ separator
    has_plus_separator = '++++' in text
    
    if has_plus_separator:
        # Split by ++++ to get separate tests
        test_sections = re.split(r'\+\+\+\+', text)
    else:
        # No ++++ separator, treat entire text as one test
        test_sections = [text]
    
    for section in test_sections:
        section = section.strip()
        if not section:
            continue
        
        questions = []
        lines = [line.strip() for line in section.split('\n') if line.strip()]
        
        current_question = None
        current_answers = []
        question_number = None
        auto_question_number = 1  # Auto-increment if no numbers found
        in_answer_section = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip separator lines
            if line.startswith('====') or line.startswith('---') or line.startswith('___'):
                in_answer_section = True
                i += 1
                continue
            
            # Check if this is a question with number (Format 1 & 2)
            question_match = re.match(r'^(\d+)\.\s*(.+)$', line)
            if question_match:
                # Save previous question if exists
                if current_question is not None:
                    if question_number is None:
                        question_number = auto_question_number
                        auto_question_number += 1
                    questions.append({
                        'question_number': question_number,
                        'question_text': current_question,
                        'answers': current_answers
                    })
                
                # Start new question
                question_number = int(question_match.group(1))
                current_question = question_match.group(2).strip()
                current_answers = []
                in_answer_section = False
                i += 1
                
                # Look for answers after the question (with ==== separator)
                while i < len(lines):
                    if lines[i].startswith('====') or lines[i].startswith('---') or lines[i].startswith('___'):
                        i += 1
                        continue
                    
                    answer_line = lines[i]
                    is_correct, answer_text = is_correct_answer_marker(answer_line)
                    
                    # Check if this is actually a new question (next number)
                    next_question_match = re.match(r'^(\d+)\.\s*(.+)$', answer_line)
                    if next_question_match:
                        break
                    
                    if answer_text:
                        current_answers.append({
                            'text': answer_text,
                            'is_correct': is_correct
                        })
                    i += 1
                
                continue
            
            # Check if this is an answer option (Format 3: a), b), c), d))
            is_option, option_letter, option_text = is_answer_option(line)
            if is_option:
                # If we don't have a question yet, this might be continuation of previous answer
                # or start of a new question without number
                if current_question is None:
                    # This is likely a new question without number
                    # Check if previous lines might be the question
                    question_lines = []
                    j = i - 1
                    while j >= 0 and not is_answer_option(lines[j])[0] and not re.match(r'^\d+\.', lines[j]):
                        if lines[j] and not lines[j].startswith('===='):
                            question_lines.insert(0, lines[j])
                        j -= 1
                    
                    if question_lines:
                        # Save previous question if exists
                        if current_question is not None:
                            if question_number is None:
                                question_number = auto_question_number
                                auto_question_number += 1
                            questions.append({
                                'question_number': question_number,
                                'question_text': current_question,
                                'answers': current_answers
                            })
                        
                        # Start new question
                        current_question = ' '.join(question_lines)
                        question_number = None  # Will use auto number
                        current_answers = []
                
                # Add answer option
                if option_text:
                    is_correct, clean_text = is_correct_answer_marker(option_text)
                    if clean_text:
                        current_answers.append({
                            'text': clean_text,
                            'is_correct': is_correct
                        })
                i += 1
                continue
            
            # Check if this is an answer after ==== separator (Format 1 & 2)
            if in_answer_section and current_question:
                is_correct, answer_text = is_correct_answer_marker(line)
                
                # Check if this is actually a new question
                next_question_match = re.match(r'^(\d+)\.\s*(.+)$', line)
                if next_question_match:
                    in_answer_section = False
                    continue
                
                if answer_text:
                    current_answers.append({
                        'text': answer_text,
                        'is_correct': is_correct
                    })
                i += 1
                continue
            
            # This might be part of a question text (if no number format)
            # Accumulate lines until we find answers
            if current_question is None:
                # Check if next lines contain answers
                has_future_answers = False
                for j in range(i + 1, min(i + 5, len(lines))):
                    if is_answer_option(lines[j])[0] or lines[j].startswith('===='):
                        has_future_answers = True
                        break
                    if re.match(r'^\d+\.', lines[j]):
                        break
                
                if has_future_answers:
                    # This is likely a question without number
                    question_lines = [line]
                    j = i + 1
                    while j < len(lines) and not is_answer_option(lines[j])[0] and not lines[j].startswith('===='):
                        if re.match(r'^\d+\.', lines[j]):
                            break
                        question_lines.append(lines[j])
                        j += 1
                    
                    if question_lines:
                        # Save previous question if exists
                        if current_question is not None:
                            if question_number is None:
                                question_number = auto_question_number
                                auto_question_number += 1
                            questions.append({
                                'question_number': question_number,
                                'question_text': current_question,
                                'answers': current_answers
                            })
                        
                        current_question = ' '.join(question_lines)
                        question_number = None  # Will use auto number
                        current_answers = []
                        i = j
                        continue
            
            i += 1
        
        # Save last question
        if current_question is not None:
            if question_number is None:
                question_number = auto_question_number
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
            return False, f"{i}-savol uchun bitta to'g'ri javob belgilanishi kerak (#, *, ✓ yoki boshqa belgi bilan)."
    
    return True, "Test muvaffaqiyatli yuklandi!"
