from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import json
from time import time

# 대시보드 웹 앱은 8000번 포트에서 실행
app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key' # flash 메시지를 위한 시크릿 키

# --- 관제실이 알고 있는 모든 '일꾼 노드'의 주소 ---
# (blockchain_node_v3.py의 ALL_PEERS와 동일하게 유지)
NODE_ADDRESSES = [
    'http://127.0.0.1:5000',
    'http://127.0.0.1:5001',
    'http://127.0.0.1:5002'
    # (여기에 5002, 5003 등을 추가하면 대시보드에 자동으로 나타남)
]

@app.route('/')
def index():
    """
    메인 대시보드 페이지.
    모든 노드의 상태를 취합하여 HTML로 렌더링합니다.
    """
    node_states = []
    
    for node_url in NODE_ADDRESSES:
        state = {
            'url': node_url,
            'online': False,
            'chain_length': 0,
            'pending_tx_count': 0
        }
        try:
            # 1. 체인 정보 요청
            response_chain = requests.get(f"{node_url}/chain", timeout=0.5)
            if response_chain.status_code == 200:
                state['online'] = True
                state['chain_length'] = response_chain.json().get('length', 0)
            
            # 2. 대기 중인 거래 정보 요청
            response_pending = requests.get(f"{node_url}/transactions/pending", timeout=0.5)
            if response_pending.status_code == 200:
                state['pending_tx_count'] = len(response_pending.json().get('transactions', []))

        except requests.exceptions.RequestException:
            state['online'] = False # 연결 실패 시 오프라인
            
        node_states.append(state)
        
    return render_template('dashboard.html', nodes=node_states)

@app.route('/mine/<port>')
def mine_on_node(port):
    """
    특정 노드에게 채굴 명령을 내립니다.
    (예: 8000/mine/5000 -> 5000번 노드에 /mine 요청)
    """
    node_url = f"http://127.0.0.1:{port}"
    try:
        response = requests.get(f"{node_url}/mine")
        if response.status_code == 200:
            flash(f"🎉 {port}번 노드 채굴 성공! (블록 전파됨)", "success")
        else:
            flash(f"❌ {port}번 노드 채굴 실패. (서버 오류)", "danger")
    except requests.exceptions.RequestException:
        flash(f"❌ {port}번 노드에 연결할 수 없습니다.", "danger")
        
    return redirect(url_for('index')) # 메인 대시보드로 복귀

@app.route('/resolve/<port>')
def resolve_on_node(port):
    """
    특정 노드에게 동기화(/nodes/resolve) 명령을 내립니다.
    """
    node_url = f"http://127.0.0.1:{port}"
    try:
        response = requests.get(f"{node_url}/nodes/resolve")
        if response.status_code == 200:
            message = response.json().get('message', '동기화 완료')
            flash(f"✅ {port}번 노드 동기화 완료: {message}", "info")
        else:
            flash(f"❌ {port}번 노드 동기화 실패.", "danger")
    except requests.exceptions.RequestException:
        flash(f"❌ {port}번 노드에 연결할 수 없습니다.", "danger")
        
    return redirect(url_for('index'))

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    """
    새로운 거래를 '모든' 노드에게 전파합니다.
    (Gossip은 1번 노드가 알아서 하겠지만, 대시보드가 모든 노드에 보내는 것이 더 확실합니다)
    """
    sender = request.form['sender']
    recipient = request.form['recipient']
    amount = request.form['amount']
    
    if not sender or not recipient or not amount:
        flash("❌ 모든 필드를 입력해야 합니다.", "danger")
        return redirect(url_for('index'))

    transaction = {
        'sender': sender,
        'recipient': recipient,
        'amount': int(amount),
        'time': time() # 고유성을 위한 타임스탬프
    }

    # 모든 노드에게 이 거래를 전파
    success_count = 0
    for node_url in NODE_ADDRESSES:
        try:
            requests.post(f"{node_url}/transactions/new", json=transaction, timeout=0.5)
            success_count += 1
        except requests.exceptions.RequestException:
            pass # (한두 개 실패해도 괜찮음)

    if success_count > 0:
        flash(f"✅ 거래가 {success_count}개의 노드에 전송되었습니다.", "success")
    else:
        flash("❌ 어떤 노드에도 거래를 전송하지 못했습니다. (모든 노드 오프라인?)", "danger")

    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)