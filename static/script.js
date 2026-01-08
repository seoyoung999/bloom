document.addEventListener('DOMContentLoaded', () => {
    // --- 전역 변수 및 요소 선택 ---
    let currentUser = null; 
    let emotionChart = null; 
    let currentRecordId = null; 

    const sections = { auth: document.getElementById('auth-section'), main: document.getElementById('main-section') };
    const forms = { login: document.getElementById('login-form'), register: document.getElementById('register-form') };
    const navLinks = { home: document.getElementById('nav-home'), history: document.getElementById('nav-history'), chatbot: document.getElementById('nav-chatbot') };
    const contentAreas = { home: document.getElementById('home-content'), history: document.getElementById('history-content'), chatbot: document.getElementById('chatbot-content') };
    const historyListEl = document.getElementById('history-list');
    const analysisResultEl = document.getElementById('analysis-result');
    const chatbotIntro = document.getElementById('chatbot-intro'); // 챗봇 안내 문구 요소 선택

    // --- 이벤트 리스너 ---
    document.getElementById('show-register').addEventListener('click', () => toggleForms(false));
    document.getElementById('show-login').addEventListener('click', () => toggleForms(true));
    document.getElementById('register-form-tag').addEventListener('submit', handleRegister);
    document.getElementById('login-form-tag').addEventListener('submit', handleLogin);
    document.getElementById('logout-btn').addEventListener('click', handleLogout);
    document.getElementById('analyze-btn').addEventListener('click', handleAnalysis);
    Object.values(navLinks).forEach(link => link.addEventListener('click', (e) => switchTab(e.target.id)));
    document.getElementById('start-chatbot-btn').addEventListener('click', startChatbot);
    
    // 기록 목록 클릭 이벤트 (이벤트 위임)
    historyListEl.addEventListener('click', (e) => {
        const targetLi = e.target.closest('.history-item');
        if (targetLi) {
            targetLi.classList.toggle('expanded');
        }
    });

    // 분석 결과 영역 내 피드백 버튼 클릭 이벤트 (이벤트 위임)
    analysisResultEl.addEventListener('click', async (e) => {
        if (e.target.classList.contains('feedback-btn')) {
            const button = e.target;
            if (button.disabled) return; 

            const challengeTitle = button.dataset.challengeTitle;
            const rating = parseInt(button.dataset.rating);
            const recordId = currentRecordId; 

            if (!currentUser || !recordId || !challengeTitle || rating === undefined) {
                console.error("피드백 전송 실패: 필수 정보 부족");
                return;
            }

            const response = await fetch('/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: currentUser,
                    record_id: recordId,
                    challenge_title: challengeTitle,
                    rating: rating
                }),
            });

            const result = await response.json();
            if (response.ok && result.success) {
                const buttonsInGroup = button.parentElement.querySelectorAll('.feedback-btn');
                buttonsInGroup.forEach(btn => {
                    btn.disabled = true;
                    if (parseInt(btn.dataset.rating) === rating) {
                        btn.classList.add('selected');
                    } else {
                        btn.classList.remove('selected');
                        btn.style.opacity = '0.5';
                    }
                });
            } else {
                alert("피드백 저장 실패: " + result.message);
            }
        }
    });

    // --- 함수 정의 ---

    // 홈 탭 초기화 함수
    function resetHomeTab() {
        const moodSlider = document.getElementById('mood-slider');
        const sleepSlider = document.getElementById('sleep-slider');
        const activitySlider = document.getElementById('activity-slider');
        
        moodSlider.value = 5;
        sleepSlider.value = 6;
        activitySlider.value = 5;

        moodSlider.dispatchEvent(new Event('input'));
        sleepSlider.dispatchEvent(new Event('input'));
        activitySlider.dispatchEvent(new Event('input'));

        document.getElementById('feeling-text').value = '';

        analysisResultEl.style.display = 'none';
        analysisResultEl.innerHTML = '';
        currentRecordId = null;
    }

    function toggleForms(showLogin) {
        forms.login.style.display = showLogin ? 'block' : 'none';
        forms.register.style.display = showLogin ? 'none' : 'block';
        document.getElementById('login-error').textContent = '';
        document.getElementById('register-error').textContent = '';
    }
    
    function switchView(viewName) {
        Object.values(sections).forEach(s => s.style.display = 'none');
        if(sections[viewName]) sections[viewName].style.display = (viewName === 'auth') ? 'flex' : 'block';
    }

    function switchTab(targetId) {
        Object.values(navLinks).forEach(link => link.classList.remove('active'));
        Object.values(contentAreas).forEach(area => area.classList.remove('active'));
        
        const targetTab = targetId.replace('nav-', '');
        navLinks[targetTab].classList.add('active');
        contentAreas[targetTab].classList.add('active');

        if (targetTab === 'home') {
            resetHomeTab();
        }
    }
    
    function showAuthError(formType, message) {
        document.getElementById(`${formType}-error`).textContent = message;
    }

    async function handleRegister(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData.entries());
        const response = await fetch('/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        const result = await response.json();
        if (response.ok) { alert(result.message); toggleForms(true); } 
        else { showAuthError('register', result.message); }
    }

    async function handleLogin(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData.entries());
        const response = await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (response.ok) {
            currentUser = data.username;
            document.getElementById('username-display').textContent = `${currentUser}님, 안녕하세요!`;
            switchView('main');
            switchTab('nav-home');
            await loadUserData();
        } else {
            const result = await response.json();
            showAuthError('login', result.message);
        }
    }

    function handleLogout() {
        currentUser = null;
        document.getElementById('login-form-tag').reset();
        switchView('auth');
        if (emotionChart) { emotionChart.destroy(); emotionChart = null; }
    }
    
    async function loadUserData() {
        if (!currentUser) return;
        const response = await fetch(`/get_data?username=${currentUser}`);
        const result = await response.json();
        if (result.success) { updateHistory(result.data); } 
        else { console.error("데이터 로드 실패:", result.message); }
    }

    async function handleAnalysis() {
        const payload = {
            username: currentUser,
            mood: parseInt(document.getElementById('mood-slider').value),
            sleep: parseInt(document.getElementById('sleep-slider').value),
            activity: parseInt(document.getElementById('activity-slider').value),
            feeling_text: document.getElementById('feeling-text').value,
        };
        const response = await fetch('/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const result = await response.json();
        if (result.success) {
            currentRecordId = result.record_id;
            displayAnalysisResult(result, {});
            await loadUserData(); 
        } else {
            alert("분석 실패: " + result.message);
        }
    }

    function displayAnalysisResult(result, feedbackGiven = {}) {
        analysisResultEl.innerHTML = `
            <h3>분석 결과</h3> 
            <p><strong>종합 점수:</strong> ${result.score} / 10</p>
            <p><strong>감정 상태:</strong> ${result.emotion_status}</p>
            <p><strong>텍스트 기반 감정:</strong> ${result.text_emotion}</p>
            <h4>추천 챌린지</h4>
            <ul class="challenge-list">
                ${result.challenges.map(c => {
                    const title = c.title;
                    const type = c.type;
                    const url = c.url;
                    const feedbackStatus = feedbackGiven[title];
                    let feedbackButtonsHTML = '';

                    if (feedbackStatus === undefined) {
                         feedbackButtonsHTML = `
                            <span class="feedback-buttons">
                                <button class="feedback-btn like" data-challenge-title="${title}" data-rating="1">👍</button>
                                <button class="feedback-btn dislike" data-challenge-title="${title}" data-rating="-1">👎</button>
                            </span>`;
                    } else {
                         feedbackButtonsHTML = `<span class="feedback-status">${feedbackStatus === 1 ? '👍 좋았어요' : '👎 별로였어요'}</span>`;
                    }
                    
                    if (url && url !== '#') {
                        return `<li><a href="${url}" target="_blank">${title} (${type})</a> ${feedbackButtonsHTML}</li>`;
                    } else {
                        return `<li class="activity-challenge">${title} (${type}) ${feedbackButtonsHTML}</li>`;
                    }
                }).join('')}
            </ul>
        `;
        analysisResultEl.style.display = 'block';
    }

    function updateHistory(historyData) {
        historyListEl.innerHTML = historyData.length > 0
            ? historyData.map(item => {
                const feedbackGiven = item.feedback_given_json ? JSON.parse(item.feedback_given_json) : {};
                const recommendedChallenges = item.recommended_challenges_json ? JSON.parse(item.recommended_challenges_json) : [];
                
                let recommendationsHTML = '<h5>추천된 챌린지:</h5><ul>';
                if (recommendedChallenges.length > 0) {
                     recommendationsHTML += recommendedChallenges.map(c => {
                         const title = c.title;
                         const status = feedbackGiven[title];
                         let statusText = '';
                         if (status === 1) statusText = ' (👍)';
                         else if (status === -1) statusText = ' (👎)';
                         
                         if (c.url && c.url !== '#') {
                             return `<li><a href="${c.url}" target="_blank">${title}</a>${statusText}</li>`;
                         } else {
                             return `<li>${title}${statusText}</li>`;
                         }
                     }).join('');
                } else {
                    recommendationsHTML += '<li>추천된 챌린지가 없습니다.</li>';
                }
                recommendationsHTML += '</ul>';

                return `<li class="history-item">
                            <div class="history-summary">
                                <span>${item.date}: ${item.score.toFixed(1)}점 (${item.status})</span>
                                <span class="toggle-icon">▼</span>
                            </div>
                            <div class="history-text">
                                <p><b>기록 내용:</b><br>${item.text || '작성된 텍스트가 없습니다.'}</p>
                                ${recommendationsHTML} 
                            </div>
                         </li>`
            }).join('')
            : '<li>기록이 없습니다.</li>';

        const ctx = document.getElementById('emotion-chart').getContext('2d');
        if (emotionChart) { emotionChart.destroy(); }
        emotionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: historyData.map(item => item.date.substring(5, 16)), 
                datasets: [{ label: '일별 감정 점수', data: historyData.map(item => item.score), borderColor: 'rgb(75, 192, 192)', tension: 0.1 }]
            },
            options: { scales: { y: { beginAtZero: true, max: 10 } } }
        });
    }

    // --- 챗봇 기능 ---
    let phq9Questions = [];
    let currentQuestionIndex = 0;
    let phq9Answers = [];

    async function startChatbot() {
        const response = await fetch('/chatbot/start');
        const data = await response.json();
        phq9Questions = data.questions;
        currentQuestionIndex = 0;
        phq9Answers = [];
        // 진단 시작 시 버튼과 안내 문구 숨김
        document.getElementById('start-chatbot-btn').style.display = 'none';
        chatbotIntro.style.display = 'none'; 
        displayNextQuestion();
    }

    function displayNextQuestion() {
        const chatbox = document.getElementById('chatbot-qna');
        if (currentQuestionIndex < phq9Questions.length) {
            const question = phq9Questions[currentQuestionIndex];
            chatbox.innerHTML = `<div class="question">${question.text}</div><div class="options">${question.options.map(opt => `<button data-score="${opt.score}">${opt.text}</button>`).join('')}</div>`;
            chatbox.querySelectorAll('.options button').forEach(btn => btn.addEventListener('click', handleChatbotAnswer));
        } else { showChatbotResult(); }
    }

    function handleChatbotAnswer(e) {
        phq9Answers.push(parseInt(e.target.dataset.score));
        currentQuestionIndex++;
        displayNextQuestion();
    }

    async function showChatbotResult() {
        const response = await fetch('/chatbot/result', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers: phq9Answers }) });
        const result = await response.json();
        const chatbox = document.getElementById('chatbot-qna');
        
        // 결과 표시: 기존 안내 문구와 시작 버튼은 숨겨진 상태 유지
        chatbox.innerHTML = `
            <h4>진단 결과</h4>
            <p>${result.message.replace(/\n/g, '<br>')}</p>
            ${result.hospital_info ? `<p class="hospital-info"><strong>도움 받을 수 있는 곳:</strong> ${result.hospital_info}</p>` : ''}
            <div class="button-wrapper" style="margin-top: 20px;">
                <button id="restart-chatbot-btn">다시 진단하기</button>
            </div>
        `;
        
        // 새로 생성된 다시 진단하기 버튼에 이벤트 연결
        document.getElementById('restart-chatbot-btn').addEventListener('click', startChatbot);
    }

    // 초기 화면 설정
    switchView('auth');
    toggleForms(true);

    // 슬라이더 값 표시 업데이트
    document.querySelectorAll('.slider-group input[type="range"]').forEach(slider => {
        const valueSpan = slider.nextElementSibling;
        const updateSliderValue = () => { valueSpan.textContent = `${slider.value}${slider.id.includes('sleep') ? '시간' : ''}`; };
        slider.addEventListener('input', updateSliderValue);
        updateSliderValue();
    });
});