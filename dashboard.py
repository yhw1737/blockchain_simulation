from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
import json
from time import time

app = Flask(__name__)
# 보안상의 이유로 SECRET_KEY가 필요합니다.
app.config['SECRET_KEY'] = 'your-very-secret-key' 

# 👈 [핵심] 하드코딩된 리스트 대신, 동적으로 관리되는 집합(Set) 사용
# 이 집합에 'http://127.0.0.1:5000' 와 같은 노드 주소가 저장됩니다.
known_nodes = set()

@app.route('/')
def index():
    """
    메인 대시보드 페이지.
    'known_nodes' 목록을 기준으로 모든 노드의 상태를 취합하여 템플릿에 전달합니다.
    """
    node_states = []
    offline_nodes = set() # 응답 없는 노드를 찾기 위함

    # 집합을 순회하는 동안 변경할 수 없으므로, 리스트로 복사해서 사용합니다.
    for node_url in list(known_nodes):
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
            state['online'] = False
            offline_nodes.add(node_url) # 응답 없는 노드를 목록에 추가
            
        node_states.append(state)
        
    # 응답 없는 노드를 'known_nodes' 목록에서 제거 (자동 복구)
    if offline_nodes:
        print(f"관제실: 응답 없음: {offline_nodes} 노드를 목록에서 제거합니다.")
        known_nodes.difference_update(offline_nodes)
        
    return render_template('dashboard.html', nodes=node_states)

@app.route('/mine/<port>')
def mine_on_node(port):
    """
    특정 노드에게 채굴 명령을 내리고 결과를 플래시 메시지로 표시합니다.
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
        
    return redirect(url_for('index'))

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
    새로운 거래를 'known_nodes' 목록에 있는 모든 노드에게 전파합니다.
    (노드들이 다시 이웃에게 전파하므로, 모든 노드가 받게 됩니다.)
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

    success_count = 0
    # 모든 노드에게 이 거래를 전파
    for node_url in list(known_nodes):
        try:
            # 이웃에게 거래를 POST하면, 그 이웃이 다시 자신의 이웃에게 전파합니다. (Gossip)
            requests.post(f"{node_url}/transactions/new", json=transaction, timeout=0.5)
            success_count += 1
        except requests.exceptions.RequestException:
            pass 

    if success_count > 0:
        flash(f"✅ 거래가 {success_count}개의 노드에 전송되었습니다. (Gossip 시작)", "success")
    else:
        flash("❌ 어떤 노드에도 거래를 전송하지 못했습니다. (모든 노드 오프라인?)", "danger")

    return redirect(url_for('index'))

# --- 노드 등록 및 해제 API ---

@app.route('/register', methods=['POST'])
def register_new_node():
    """
    새로운 노드가 실행될 때 호출하는 API. (노드가 관제실에 스스로를 등록)
    1. 기존 노드들에게 새 노드를 소개(add_peer)합니다.
    2. 새 노드를 'known_nodes'에 추가합니다.
    3. 새 노드에게 기존 노드 목록을 반환합니다.
    """
    values = request.get_json()
    port = values.get('port')
    if not port:
        return "오류: 'port' 값이 누락되었습니다.", 400
    
    new_node_url = f"http://127.0.0.1:{port}"
    
    # 2. 기존 노드들에게 새 노드를 소개 (5000번에게 5001번을 이웃으로 등록 요청)
    existing_peers = list(known_nodes) 
    for peer_url in existing_peers:
        try:
            requests.post(f"{peer_url}/add_peer", json={'peer_url': new_node_url}, timeout=0.5)
        except requests.exceptions.RequestException:
            pass 

    # 1. 새 노드를 목록에 추가
    known_nodes.add(new_node_url)
    print(f"관제실: 새 노드 {new_node_url} 등록 완료. 현재 총 {len(known_nodes)}개 노드.")
    
    # 3. 새 노드에게 기존 이웃 목록 반환
    return jsonify({'peers': existing_peers})

@app.route('/unregister', methods=['POST'])
def unregister_node():
    """
    노드가 종료될 때 호출하는 API (atexit).
    """
    values = request.get_json()
    port = values.get('port')
    if not port:
        return "오류: 'port' 값이 누락되었습니다.", 400
        
    node_url = f"http://127.0.0.1:{port}"
    known_nodes.discard(node_url) 
    print(f"관제실: {node_url} 노드 등록 해제. 현재 총 {len(known_nodes)}개 노드.")
    
    return "등록 해제 완료", 200

if __name__ == '__main__':
    print("관제실 서버를 http://127.0.0.1:8000 에서 시작합니다...")
    app.run(host='0.0.0.0', port=8000, debug=True)