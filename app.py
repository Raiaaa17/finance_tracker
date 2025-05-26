from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
from supabase import create_client, Client
from datetime import datetime, timedelta
from google import genai
from google.genai import types
import json
from collections import defaultdict
from calendar import monthrange
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

# Global clients with better initialization handling
supabase_client = None
gemini_client = None

def get_supabase_client():
    global supabase_client
    try:
        if supabase_client is None:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                logger.error("Missing Supabase credentials")
                return None
            
            # Add timeout and retries for serverless environment    
            supabase_client = create_client(
                supabase_url, 
                supabase_key,
                options={
                    'timeout': 5,  # 5 seconds timeout
                    'retries': 3,  # 3 retries
                    'autoRefreshToken': False  # Disable token refresh in serverless
                }
            )
            logger.info("Supabase client initialized successfully")
        return supabase_client
    except Exception as e:
        logger.error(f"Supabase client initialization error: {str(e)}")
        return None

def get_gemini_client():
    global gemini_client
    try:
        if gemini_client is None:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                logger.error("Missing Gemini API key")
                return None
                
            gemini_client = genai.Client(api_key=gemini_key)
            logger.info("Gemini AI client initialized successfully")
        return gemini_client
    except Exception as e:
        logger.error(f"Gemini client initialization error: {str(e)}")
        return None

def init_clients():
    """Initialize both clients and return success status"""
    supabase = get_supabase_client()
    gemini = get_gemini_client()
    return supabase is not None and gemini is not None

@app.before_request
def before_request():
    """Ensure clients are initialized before each request"""
    if request.path == '/api/health':
        return None
        
    if not init_clients():
        error_msg = "Failed to initialize required services. Please check your environment variables and try again."
        logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

# Add a health check endpoint
@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

EXPENSE_CATEGORIES = [
    "Food & Dining",
    "Transportation",
    "Shopping",
    "Bills & Utilities",
    "Entertainment"
]

# Define the function declaration for expense analysis
analyze_expense_function = {
    "name": "analyze_expense",
    "description": "Analyzes an expense description to extract name, amount, and category.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "A concise name for the expense",
            },
            "amount": {
                "type": "number",
                "description": "The amount of the expense (numeric value only)",
            },
            "category": {
                "type": "string",
                "enum": EXPENSE_CATEGORIES,
                "description": "The category of the expense",
            }
        },
        "required": ["name", "amount", "category"],
    },
}

def analyze_expense_with_gemini(description: str):
    try:
        gemini = get_gemini_client()
        if not gemini:
            raise ValueError("Gemini client not initialized")
            
        tools = types.Tool(function_declarations=[analyze_expense_function])
        config = types.GenerateContentConfig(tools=[tools])
        
        prompt = f"""
        Analyze this expense description and extract the expense details:
        Description: {description}
        
        Please extract:
        1. A concise name for the expense
        2. The amount (as a number)
        3. The most appropriate category from: {', '.join(EXPENSE_CATEGORIES)}
        
        If the amount is not explicitly stated, make a reasonable estimate based on context.
        If no clear category fits, choose the closest match.
        """
        
        response = gemini.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=config
        )
        
        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            return function_call.args
        else:
            raise ValueError("AI could not analyze the expense properly")
    except Exception as e:
        logger.error(f"Error in analyze_expense_with_gemini: {str(e)}")
        raise ValueError(f"Error analyzing expense: {str(e)}")

def get_top_categories(category_totals, limit=5):
    # Sort categories by amount in descending order and get top N
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    return sorted_categories[:limit]

def get_time_series_data(expenses, period='monthly'):
    """Get time series data grouped by period and optionally by category"""
    try:
        # Get the date range
        now = datetime.utcnow()
        
        # Calculate date ranges and initialize data structures
        if period == 'daily':
            # Last 30 days
            dates = [(now - timedelta(days=x)) for x in range(29, -1, -1)]
            date_keys = [d.strftime('%Y-%m-%d') for d in dates]
        elif period == 'weekly':
            # Last 12 weeks - start from the beginning of current week
            current = now - timedelta(days=now.weekday())
            dates = [(current - timedelta(weeks=x)) for x in range(11, -1, -1)]
            date_keys = [d.strftime('%Y-W%V') for d in dates]
        else:  # monthly
            # Last 12 months - start from the beginning of current month
            current = now.replace(day=1)
            dates = []
            for i in range(11, -1, -1):
                year = current.year
                month = current.month - i
                if month <= 0:
                    year -= 1
                    month += 12
                dates.append(current.replace(year=year, month=month, day=1))
            date_keys = [d.strftime('%Y-%m') for d in dates]

        # Initialize data structures with zeros
        time_series = {key: 0 for key in date_keys}
        categories = set(expense['category'] for expense in expenses)
        category_series = {cat: {key: 0 for key in date_keys} for cat in categories}

        logger.info(f"Processing {period} data for date range: {date_keys[0]} to {date_keys[-1]}")
        logger.info(f"Found categories: {categories}")

        # Process expenses
        for expense in expenses:
            try:
                date_str = expense['created_at']
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                amount = float(expense['amount'])
                category = expense['category']

                # Get the appropriate key based on period
                if period == 'daily':
                    key = date_obj.strftime('%Y-%m-%d')
                elif period == 'weekly':
                    key = date_obj.strftime('%Y-W%V')
                else:  # monthly
                    key = date_obj.strftime('%Y-%m')

                # Only process if the key is in our date range
                if key in time_series:
                    time_series[key] += amount
                    if category in category_series:
                        category_series[category][key] += amount

            except Exception as exp_error:
                logger.error(f"Error processing expense: {str(exp_error)}")
                continue

        # Convert to sorted lists of tuples
        sorted_times = [(key, time_series[key]) for key in date_keys]
        sorted_categories = {
            category: [(key, amounts[key]) for key in date_keys]
            for category, amounts in category_series.items()
        }

        logger.info(f"Generated {period} time series with {len(sorted_times)} data points")
        logger.info(f"Time periods: {date_keys}")
        logger.info(f"Category data points: {[len(cat_data) for cat_data in sorted_categories.values()]}")

        return {
            'total': sorted_times,
            'by_category': sorted_categories
        }

    except Exception as e:
        logger.error(f"Error generating {period} time series: {str(e)}")
        return {
            'total': [],
            'by_category': {}
        }

def get_dashboard_data():
    try:
        # Get all expenses
        logger.info("Fetching expenses from database...")
        result = supabase_client.table('expenses').select('*').order('created_at', desc=True).execute()
        
        if not result:
            logger.error("No result returned from Supabase")
            return None
            
        if not hasattr(result, 'data'):
            logger.error("Result missing data attribute")
            return None
            
        expenses = result.data
        logger.info(f"Retrieved {len(expenses)} expenses from database")

        # Initialize default response
        dashboard_data = {
            'total_expenses': 0,
            'category_totals': {},
            'top_categories': [],
            'time_series': {
                'daily': {'total': [], 'by_category': {}},
                'weekly': {'total': [], 'by_category': {}},
                'monthly': {'total': [], 'by_category': {}}
            },
            'recent_expenses': [],
            'avg_daily_expense': 0,
            'current_month_total': 0,
            'mom_growth': 0
        }

        if not expenses:
            logger.info("No expenses found in database")
            return dashboard_data

        try:
            # Calculate total expenses
            dashboard_data['total_expenses'] = sum(expense['amount'] for expense in expenses)
            logger.info(f"Total expenses: {dashboard_data['total_expenses']}")

            # Calculate category totals
            category_totals = defaultdict(float)
            for expense in expenses:
                category_totals[expense['category']] += expense['amount']
            dashboard_data['category_totals'] = dict(category_totals)
            logger.info(f"Category totals: {dashboard_data['category_totals']}")

            # Get top categories
            dashboard_data['top_categories'] = get_top_categories(dict(category_totals))
            logger.info(f"Top categories: {dashboard_data['top_categories']}")

            # Get time series data for different periods
            logger.info("Calculating time series data...")
            dashboard_data['time_series'] = {
                'daily': get_time_series_data(expenses, 'daily'),
                'weekly': get_time_series_data(expenses, 'weekly'),
                'monthly': get_time_series_data(expenses, 'monthly')
            }
            logger.info("Time series data calculated")

            # Get recent expenses (last 5)
            dashboard_data['recent_expenses'] = expenses[:5] if expenses else []
            logger.info(f"Recent expenses count: {len(dashboard_data['recent_expenses'])}")

            # Calculate average daily expense
            daily_data = dashboard_data['time_series']['daily']['total']
            if daily_data:
                dashboard_data['avg_daily_expense'] = sum(amount for _, amount in daily_data) / len(daily_data)
                logger.info(f"Average daily expense: {dashboard_data['avg_daily_expense']}")

            # Get current month's total
            current_month = datetime.utcnow().strftime('%Y-%m')
            monthly_data = dashboard_data['time_series']['monthly']['total']
            dashboard_data['current_month_total'] = sum(
                amount for date, amount in monthly_data if date == current_month
            )
            logger.info(f"Current month total: {dashboard_data['current_month_total']}")

            # Calculate month-over-month growth
            if len(monthly_data) >= 2:
                current = monthly_data[-1][1]
                previous = monthly_data[-2][1]
                dashboard_data['mom_growth'] = ((current - previous) / previous * 100) if previous > 0 else 0
                logger.info(f"Month-over-month growth: {dashboard_data['mom_growth']}%")

            return dashboard_data

        except Exception as calc_error:
            logger.error(f"Error calculating dashboard data: {str(calc_error)}")
            raise

    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@app.route('/')
def index():
    try:
        logger.info("Fetching dashboard data...")
        dashboard_data = get_dashboard_data()
        
        if dashboard_data is None:
            logger.error("Failed to get dashboard data")
            raise Exception("Failed to get dashboard data")
        
        logger.info(f"Dashboard data retrieved successfully: {json.dumps(dashboard_data, default=str)}")
            
        return render_template(
            'index.html',
            categories=EXPENSE_CATEGORIES,
            dashboard=dashboard_data
        )
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        # Return a safe default structure
        empty_dashboard = {
            'total_expenses': 0,
            'category_totals': {},
            'top_categories': [],
            'time_series': {
                'daily': {'total': [], 'by_category': {}},
                'weekly': {'total': [], 'by_category': {}},
                'monthly': {'total': [], 'by_category': {}}
            },
            'recent_expenses': [],
            'avg_daily_expense': 0,
            'current_month_total': 0,
            'mom_growth': 0
        }
        return render_template(
            'index.html',
            categories=EXPENSE_CATEGORIES,
            dashboard=empty_dashboard,
            error=str(e)
        )

@app.route('/api/analyze-expense', methods=['POST'])
def process_expense():
    try:
        data = request.get_json()
        if not data or 'description' not in data:
            logger.warning("Invalid request: missing description")
            return jsonify({'error': 'Description is required'}), 400
            
        description = data['description'].strip()
        if not description:
            logger.warning("Invalid request: empty description")
            return jsonify({'error': 'Description cannot be empty'}), 400
        
        logger.info(f"Analyzing expense: {description}")
        analysis = analyze_expense_with_gemini(description)
        
        # Validate analysis results
        if not all(key in analysis for key in ['name', 'amount', 'category']):
            logger.error("Invalid analysis result from AI")
            return jsonify({'error': 'Invalid analysis result from AI'}), 500
            
        # Ensure amount is a valid number
        try:
            amount = float(analysis['amount'])
            analysis['amount'] = amount
        except (ValueError, TypeError):
            logger.error("Invalid amount value in analysis")
            return jsonify({'error': 'Invalid amount value'}), 500
            
        # Store in Supabase
        expense_data = {
            'description': description,
            'name': analysis['name'],
            'amount': analysis['amount'],
            'category': analysis['category'],
            'created_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Storing expense in database: {expense_data}")
        result = supabase_client.table('expenses').insert(expense_data).execute()
        
        if not result.data:
            logger.error("Failed to store expense in database")
            return jsonify({'error': 'Failed to store expense'}), 500
        
        logger.info("Expense stored successfully")
        return jsonify({
            'success': True,
            'analysis': analysis,
            'data': result.data
        })
    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/expense/<expense_id>', methods=['PUT'])
def update_expense(expense_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        # Validate required fields
        required_fields = ['name', 'amount', 'category', 'description']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
            
        # Validate amount
        try:
            amount = float(data['amount'])
            if amount <= 0:
                return jsonify({'error': 'Amount must be greater than 0'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount value'}), 400
            
        update_data = {
            'name': data['name'].strip(),
            'amount': amount,
            'category': data['category'],
            'description': data['description'].strip()
        }
        
        result = supabase_client.table('expenses').update(update_data).eq('id', expense_id).execute()
        
        if not result.data:
            return jsonify({'error': 'Expense not found'}), 404
            
        return jsonify({
            'success': True,
            'data': result.data
        })
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/expense/<expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    try:
        result = supabase_client.table('expenses').delete().eq('id', expense_id).execute()
        
        if not result.data:
            return jsonify({'error': 'Expense not found'}), 404
            
        return jsonify({
            'success': True,
            'data': result.data
        })
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/test-db')
def test_db():
    try:
        # Test database connection
        logger.info("Testing database connection...")
        result = supabase_client.table('expenses').select('count').execute()
        if not result or not hasattr(result, 'data'):
            raise Exception("Could not connect to database")
            
        # Test data retrieval
        result = supabase_client.table('expenses').select('*').limit(1).execute()
        expenses = result.data if result and hasattr(result, 'data') else []
        
        return jsonify({
            'status': 'success',
            'connection': 'ok',
            'has_data': len(expenses) > 0,
            'sample_data': expenses[0] if expenses else None
        })
    except Exception as e:
        logger.error(f"Database test failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

def verify_db_connection():
    try:
        logger.info("Verifying database connection...")
        result = supabase_client.table('expenses').select('count').execute()
        if not result or not hasattr(result, 'data'):
            raise Exception("Could not connect to database")
        logger.info("Database connection verified")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return False

@app.before_request
def check_db_connection():
    if request.endpoint != 'test_db' and not verify_db_connection():
        return jsonify({
            'error': 'Database connection error. Please check your configuration.'
        }), 500

def safe_db_operation(operation):
    """Wrapper for safe database operations with retries"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = get_supabase_client()
            if not client:
                raise Exception("Failed to initialize Supabase client")
            return operation(client)
        except Exception as e:
            logger.error(f"Database operation failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                raise
            continue

@app.route('/api/expenses')
def get_all_expenses():
    try:
        def fetch_expenses(client):
            result = client.table('expenses').select('*').order('created_at', desc=True).execute()
            if not result or not hasattr(result, 'data'):
                raise Exception("Failed to fetch expenses from database")
            return result.data
            
        expenses = safe_db_operation(fetch_expenses)
        logger.info(f"Successfully fetched {len(expenses)} expenses")
        return jsonify(expenses)
    except Exception as e:
        logger.error(f"Error fetching expenses: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/expense', methods=['POST'])
def create_expense():
    try:
        data = request.json
        required_fields = ['name', 'amount', 'category', 'description', 'created_at']
        
        # Validate required fields
        if not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
            
        # Validate amount is a positive number
        try:
            amount = float(data['amount'])
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid amount'
            }), 400
            
        # Validate category
        if data['category'] not in EXPENSE_CATEGORIES:
            return jsonify({
                'success': False,
                'error': 'Invalid category'
            }), 400
            
        # Create expense in database using safe operation
        def insert_expense(client):
            result = client.table('expenses').insert({
                'name': data['name'],
                'amount': amount,
                'category': data['category'],
                'description': data['description'],
                'created_at': data['created_at']
            }).execute()
            
            if not result.data:
                raise Exception("No data returned from database")
            return result.data[0]
            
        expense_data = safe_db_operation(insert_expense)
        return jsonify({
            'success': True,
            'data': expense_data
        })
        
    except Exception as e:
        logger.error(f"Error creating expense: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Vercel handler
app.debug = False

if __name__ == '__main__':
    init_clients()
    app.run()
else:
    # For Vercel serverless environment
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )
    # Initialize clients on cold start
    init_clients() 