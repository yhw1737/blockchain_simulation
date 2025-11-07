import hashlib
import json
from time import time
from uuid import uuid4
from flask import Flask, jsonify, request
import requests 
from urllib.parse import urlparse
import os

# --- (하드코딩된 GENESIS_BLOCK) ---
# (이전과 동일)
GENESIS_MERKLE_ROOT = hashlib.sha256(json.dumps([], sort_keys=True).encode()).hexdigest()
GENESIS_BLOCK = {
    'index': 1,
    'timestamp': 1500000000, 
    'transactions': [],
    'proof': 100, 
    'previous_hash': '1',
    'merkle_root': GENESIS_MERKLE_ROOT 
}

class Blockchain:
    def __init__(self):
        self.chain = [GENESIS_BLOCK] 
        self.current_transactions = []
        self.nodes = set()
        
    def new_block(self, proof, previous_hash=None):
        merkle_root = hashlib.sha256(json.dumps(self.current_transactions, sort_keys=True).encode()).hexdigest()
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.last_block),
            'merkle_root': merkle_root 
        }
        self.current_transactions = []
        self.chain.append(block)
        return block

    def new_transaction(self, transaction):
        tx_to_store = transaction.copy() 
        tx_to_store.pop('propagated', None) 
        if tx_to_store not in self.current_transactions:
            self.current_transactions.append(tx_to_store)
            return self.last_block['index'] + 1
        return None

    @staticmethod
    def hash(block):
        # 👈 [수정] .get()을 사용하여 키가 없는 구버전 블록에서도 오류가 나지 않게 방어
        block_header = {
            'index': block['index'],
            'timestamp': block['timestamp'],
            'proof': block['proof'],
            'previous_hash': block['previous_hash'],
            'merkle_root': block.get('merkle_root', '') # 👈 get()으로 변경
        }
        block_string = json.dumps(block_header, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        # ... (동일) ...
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        # ... (동일) ...
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"
        
    def validate_chain(self, chain):
        # ... (제네시스 블록 검증 ... 동일) ...
        if chain[0] != GENESIS_BLOCK:
            print(f"🚨 검증 실패: 0번 블록(제네시스 블록)이 네트워크 표준과 다릅니다!")
            return False

        previous_block = chain[0]
        block_index = 1

        while block_index < len(chain):
            current_block = chain[block_index]
            # ... (해시 연결, PoW 검증 ... 동일) ...
            if current_block['previous_hash'] != self.hash(previous_block):
                print(f"🚨 검증 실패: 블록 {current_block['index']}의 'previous_hash' 불일치.")
                return False
            if not self.valid_proof(previous_block['proof'], current_block['proof']):
                print(f"🚨 검증 실패: 블록 {current_block['index']}의 작업 증명(proof) 실패.")
                return False
            
            # ... (머클 루트 검증 ... 동일) ...
            tx_hash_check = hashlib.sha256(json.dumps(current_block['transactions'], sort_keys=True).encode()).hexdigest()
            
            # 👈 [수정] .get()을 사용하여 키가 없는 구버전 블록에서도 오류가 나지 않게 방어
            stored_merkle_root = current_block.get('merkle_root') 
            if stored_merkle_root is None or stored_merkle_root != tx_hash_check: 
                print(f"🚨 검증 실패: 블록 {current_block['index']}의 거래 내역(merkle_root)이 조작되었거나 형식이 맞지 않습니다.")
                print(f"   - 저장된 Merkle Root: {stored_merkle_root}")
                print(f"   - 계산된 Merkle Root: {tx_hash_check}")
                return False

            previous_block = current_block
            block_index += 1
        
        print(f"✅ 체인 검증 성공 (길이: {len(chain)})")
        return True

    # ... (register_node, resolve_conflicts, save, load ... 동일) ...
    def register_node(self, address):
        # ... (동일) ...
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('잘못된 URL입니다.')

    def resolve_conflicts(self):
        # ... (동일) ...
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)

        for node in neighbours:
            try:
                response = requests.get(f'http://{node}/chain')
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']
                    if length > max_length and self.validate_chain(chain):
                        max_length = length
                        new_chain = chain
            except requests.exceptions.RequestException as e:
                print(f"노드 {node}에 연결할 수 없습니다: {e}")

        if new_chain:
            self.chain = new_chain
            self.save_chain_to_json() 
            return True
        return False

    def save_chain_to_json(self):
        # ... (동일) ...
        with open(f"blockchain_{app.config['PORT']}.json", "w", encoding="utf-8") as f:
            json.dump(self.chain, f, indent=4, ensure_ascii=False)

    def load_chain_from_json(self, port):
        # ... (동일) ...
        filepath = f"blockchain_{port}.json"
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    loaded_chain = json.load(f)
                if self.validate_chain(loaded_chain):
                    self.chain = loaded_chain
                    print(f"성공: {filepath}에서 체인을 검증하고 로드했습니다.")
                else:
                    print(f"🚨 치명적 오류: {filepath} 파일이 손상되었습니다! 프로그램을 중단합니다.")
                    exit()
            except json.JSONDecodeError:
                print(f"오류: {filepath} 파일을 읽을 수 없습니다.")
                exit()
        else:
            print(f"새로운 {filepath} 파일을 생성합니다. (제네시스 블록 기반)")
            self.save_chain_to_json()


# --- Flask 웹 서버 설정 ---
app = Flask(__name__)
node_identifier = str(uuid4()).replace('-', '')
blockchain = Blockchain() 

# --- (API 엔드포인트) ---

@app.route('/mine', methods=['GET'])
def mine():
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # 👈 [버그 수정] 3개 인자가 아닌, 1개의 딕셔너리로 보상 거래 생성
    reward_transaction = {
        "sender": "0",
        "recipient": node_identifier,
        "amount": 1,
        "time": time() # 👈 time 필드 추가
    }
    blockchain.new_transaction(reward_transaction)

    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)
    blockchain.save_chain_to_json()

    # 👈 블록 전파 (모든 이웃에게 새 블록 '푸시')
    for node in blockchain.nodes:
        try:
            requests.post(f'http://{node}/blocks/receive', json=block)
        except requests.exceptions.RequestException:
            print(f"노드 {node}에게 블록 전파 실패")

    response = {
        'message': "새로운 블록 채굴 성공!",
        'block': block
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    
    # 👈 [수정] 'time'을 필수 필드로 지정
    required = ['sender', 'recipient', 'amount', 'time'] 
    if not all(k in values for k in required):
        return '필수 값이 누락되었습니다. (sender, recipient, amount, time)', 400

    index = blockchain.new_transaction(values) 
    
    if index is None:
        response = {'message': '이미 존재하는 트랜잭션입니다.'}
        return jsonify(response), 200

    # 👈 거래 전파 (Gossip)
    is_propagated = values.get('propagated', False)
    if not is_propagated:
        values['propagated'] = True 
        for node in blockchain.nodes:
            try:
                requests.post(f'http://{node}/transactions/new', json=values)
            except requests.exceptions.RequestException:
                print(f"노드 {node}에게 거래 전파 실패")

    response = {'message': f'거래가 블록 {index}에 추가될 예정입니다.'}
    return jsonify(response), 201

@app.route('/blocks/receive', methods=['POST'])
def receive_block():
    # ... (동일) ...
    new_block = request.get_json()
    last_block = blockchain.last_block
    
    if new_block['previous_hash'] != blockchain.hash(last_block):
        # [수정] 내 체인이 더 짧을 수도 있으니, /resolve를 요청
        if new_block['index'] > last_block['index'] + 1:
            print(f"수신한 블록 #{new_block['index']}이 내 체인보다 너무 깁니다. 전체 동기화(/resolve)가 필요합니다.")
            return "체인 동기화 필요", 409 # 409 Conflict
        return "오류: 블록의 previous_hash가 일치하지 않습니다.", 400
        
    if not blockchain.valid_proof(last_block['proof'], new_block['proof']):
        return "오류: 블록의 작업 증명이 유효하지 않습니다.", 400
        
    if new_block['index'] <= last_block['index']:
        return "이미 최신 블록을 가지고 있습니다.", 200

    # 👈 [추가] 수신한 블록의 거래내역(merkle_root)도 검증
    tx_hash_check = hashlib.sha256(json.dumps(new_block['transactions'], sort_keys=True).encode()).hexdigest()
    if new_block.get('merkle_root') != tx_hash_check:
        return "오류: 수신한 블록의 거래 내역(merkle_root)이 조작되었습니다.", 400

    # [수정] 받은 블록의 거래가 내 대기 목록에 있다면 제거
    new_tx_list = [json.dumps(tx, sort_keys=True) for tx in new_block['transactions']]
    temp_transactions = []
    for tx in blockchain.current_transactions:
        if json.dumps(tx, sort_keys=True) not in new_tx_list:
            temp_transactions.append(tx)
    blockchain.current_transactions = temp_transactions
    
    blockchain.chain.append(new_block)
    blockchain.save_chain_to_json()
    
    print(f"🎉 블록 #{new_block['index']}을(를) 네트워크로부터 수신 및 동기화했습니다.")
    return "블록 수신 완료", 201


@app.route('/chain', methods=['GET'])
def full_chain():
    # ... (동일) ...
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/transactions/pending', methods=['GET'])
def get_pending_transactions():
    # ... (동일) ...
    response = {
        'message': '현재 대기 중인 트랜잭션 목록',
        'transactions': blockchain.current_transactions
    }
    return jsonify(response), 200

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    # ... (동일) ...
    replaced = blockchain.resolve_conflicts()
    if replaced:
        response = {'message': '체인이 교체되었습니다. (더 긴 체인 발견)', 'new_chain': blockchain.chain}
    else:
        response = {'message': '현재 체인이 가장 최신입니다.', 'chain': blockchain.chain}
    return jsonify(response), 200

# --- (서버 실행 및 자동 이웃 등록 부분은 이전과 동일) ---
if __name__ == '__main__':
    from argparse import ArgumentParser
    
    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='서버가 실행될 포트 번호')
    args = parser.parse_args()
    port = args.port
    
    app.config['PORT'] = port 
    
    blockchain.load_chain_from_json(port) 
    
    ALL_PEERS = [
        'http://127.0.0.1:5000',
        'http://127.0.0.1:5001'
    ]
    
    my_address = f"http://127.0.0.1:{port}" 
    
    for peer_address in ALL_PEERS:
        parsed_url = urlparse(peer_address)
        if parsed_url.netloc != f"127.0.0.1:{port}": 
            print(f"[{port}번 노드] 이웃 노드로 {peer_address}를 등록 시도합니다.")
            blockchain.register_node(peer_address)

    # 👈 [핵심 수정]
    # 서버를 시작하기 전, 네트워크에 접속하여 가장 긴 체인을 받아옵니다.
    # (Initial Block Download - IBD)
    print(f"[{port}번 노드] 서버 시작 전, 네트워크 동기화를 시도합니다...")
    replaced = blockchain.resolve_conflicts()
    if replaced:
        print(f"[{port}번 노드] 동기화 완료: 네트워크에서 더 긴 체인을 받아왔습니다.")
    else:
        print(f"[{port}번 노드] 동기화 완료: 이미 최신 체인을 가지고 있습니다.")
    # --------------------------------------------------

    print(f"[{port}번 노드] http://127.0.0.1:{port} 에서 서버를 시작합니다.")

    app.run(host='0.0.0.0', port=port)