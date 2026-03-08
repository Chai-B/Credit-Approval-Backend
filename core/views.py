import datetime, pandas as pd
from celery import shared_task
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Customer, Loan

def calc_emi(p, r, n):
    if r <= 0: return round(p / n, 2) if n else 0
    r = r / 1200
    expr = (1 + r) ** n
    return round((p * r * expr) / (expr - 1), 2)

def calc_score(c):
    loans = c.loans.all()
    if sum(l.loan_amount for l in loans if l.is_approved) > c.approved_limit: return 0
    if not loans: return 50
    emis, paid = sum(l.tenure for l in loans), sum(l.emis_paid_on_time for l in loans)
    s_pay = int((paid / emis * 40) if emis else 0)
    s_cnt = 20 if len(loans) > 2 else len(loans) * 10
    s_act = 20 if any(l.start_date.year == datetime.date.today().year for l in loans) else 10
    s_vol = int(min(sum(l.loan_amount for l in loans) / (c.approved_limit or 1), 1) * 20)
    return max(0, min(100, s_pay + s_cnt + s_act + s_vol))

def eligibility(c, amt, rate, n):
    score = calc_score(c)
    curr_emi = c.loans.filter(is_approved=True).aggregate(Sum('monthly_repayment'))['monthly_repayment__sum'] or 0
    if curr_emi + calc_emi(amt, rate, n) > c.monthly_salary * 0.5: return False, rate, "sorry, your emi would cross 50% of your monthly salary"
    if score > 50: return True, rate, "loan approved"
    if score > 30: return True, max(12.0, rate), "loan approved but we had to increase the interest rate"
    if score > 10: return True, max(16.0, rate), "loan approved but your score requires a higher interest rate"
    return False, rate, "we cant approve this loan because of low credit score"

@shared_task
def ingest():
    try:
        cd = pd.read_excel('data/customer_data.xlsx').fillna(0)
        Customer.objects.bulk_create([
            Customer(
                customer_id=r['Customer ID'], first_name=r['First Name'], last_name=r['Last Name'], 
                phone_number=r['Phone Number'], age=r.get('Age', 0), monthly_salary=r['Monthly Salary'],
                approved_limit=r['Approved Limit'], current_debt=r.get('current_debt', 0)
            ) for _, r in cd.iterrows()
        ], ignore_conflicts=True)
        ld = pd.read_excel('data/loan_data.xlsx').fillna(0)
        cids = set(Customer.objects.values_list('customer_id', flat=True))
        Loan.objects.bulk_create([
            Loan(
                loan_id=r['Loan ID'], customer_id=r['Customer ID'], loan_amount=r['Loan Amount'], 
                tenure=r['Tenure'], interest_rate=r['Interest Rate'], monthly_repayment=r.get('Monthly payment', 0),
                emis_paid_on_time=r.get('EMIs paid on Time', 0), start_date=r['Date of Approval'],
                end_date=r['End Date'] if str(r['End Date']).strip() else None, is_approved=True
            ) for _, r in ld.iterrows() if r['Customer ID'] in cids
        ], ignore_conflicts=True)
        from django.db import connection
        with connection.cursor() as c:
            c.execute("SELECT setval(pg_get_serial_sequence('core_customer', 'customer_id'), coalesce(max(customer_id), 1), max(customer_id) is not null) FROM core_customer;")
            c.execute("SELECT setval(pg_get_serial_sequence('core_loan', 'loan_id'), coalesce(max(loan_id), 1), max(loan_id) is not null) FROM core_loan;")
    except Exception as e: print(e)

class Register(APIView):
    def post(self, r):
        sal = int(r.data.get('monthly_income', 0))
        c = Customer.objects.create(
            first_name=r.data['first_name'], last_name=r.data['last_name'], age=r.data['age'], 
            monthly_salary=sal, phone_number=r.data['phone_number'], approved_limit=int(round(sal * 36 / 100000) * 100000)
        )
        return Response({
            "customer_id": c.customer_id, "name": f"{c.first_name} {c.last_name}",
            "age": c.age, "monthly_income": c.monthly_salary,
            "approved_limit": c.approved_limit, "phone_number": c.phone_number
        }, status=201)

class Check(APIView):
    def post(self, r):
        c = get_object_or_404(Customer, pk=r.data['customer_id'])
        appr, rate, _ = eligibility(c, r.data['loan_amount'], r.data['interest_rate'], r.data['tenure'])
        return Response({
            "customer_id": c.customer_id, "approval": appr, "interest_rate": r.data['interest_rate'], 
            "corrected_interest_rate": rate, "tenure": r.data['tenure'], 
            "monthly_installment": calc_emi(r.data['loan_amount'], rate, r.data['tenure'])
        })

class Create(APIView):
    def post(self, r):
        c = get_object_or_404(Customer, pk=r.data['customer_id'])
        appr, rate, msg = eligibility(c, r.data['loan_amount'], r.data['interest_rate'], r.data['tenure'])
        emi = calc_emi(r.data['loan_amount'], rate, r.data['tenure'])
        l_id = None
        if appr:
            l = Loan.objects.create(
                customer=c, loan_amount=r.data['loan_amount'], tenure=r.data['tenure'],
                interest_rate=rate, monthly_repayment=emi, is_approved=True
            )
            l_id = l.loan_id
            c.current_debt += r.data['loan_amount']
            c.save(update_fields=['current_debt'])
        return Response({
            "loan_id": l_id, "customer_id": c.customer_id, "loan_approved": appr,
            "message": msg, "monthly_installment": emi
        }, status=201 if appr else 200)

class ViewOne(APIView):
    def get(self, r, loan_id):
        l = get_object_or_404(Loan, pk=loan_id, is_approved=True)
        return Response({
            "loan_id": l.loan_id, "customer": {
                "id": l.customer.customer_id, "first_name": l.customer.first_name, 
                "last_name": l.customer.last_name, "phone_number": l.customer.phone_number, "age": l.customer.age
            },
            "loan_amount": l.loan_amount, "interest_rate": l.interest_rate,
            "monthly_installment": l.monthly_repayment, "tenure": l.tenure
        })

class ViewAll(APIView):
    def get(self, r, customer_id):
        return Response([{
            "loan_id": x.loan_id, "loan_amount": x.loan_amount, "interest_rate": x.interest_rate, 
            "monthly_installment": x.monthly_repayment, "repayments_left": max(0, x.tenure - x.emis_paid_on_time)
        } for x in Loan.objects.filter(customer_id=customer_id, is_approved=True)])

urlpatterns = [
    path('register', Register.as_view()),
    path('check-eligibility', Check.as_view()),
    path('create-loan', Create.as_view()),
    path('view-loan/<int:loan_id>', ViewOne.as_view()),
    path('view-loans/<int:customer_id>', ViewAll.as_view())
]
