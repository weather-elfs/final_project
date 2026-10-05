import { useState, type FormEvent } from 'react';

import { login } from '../../api';

interface LoginPageProps {
  onAuthenticated: (center: { id: string; name: string }) => void;
}

export default function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [centerId, setCenterId] = useState(() => localStorage.getItem('weather-center-id') ?? '');
  const [password, setPassword] = useState('');
  const [rememberId, setRememberId] = useState(Boolean(centerId));
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!centerId.trim() || !password) {
      setError('센터 ID와 비밀번호를 모두 입력하세요.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const response = await login(centerId.trim(), password);
      if (rememberId) localStorage.setItem('weather-center-id', centerId.trim());
      else localStorage.removeItem('weather-center-id');
      onAuthenticated(response.data.center);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : '로그인 요청을 처리하지 못했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="weather-ui login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand" aria-label="기상 데이터 지상국">
          <span aria-hidden="true">W</span>
          <strong>기상 데이터 지상국</strong>
        </div>
        <header>
          <h1 id="login-title">저시정 상황판</h1>
          <p>로그인 후 사용가능 합니다.</p>
        </header>
        <form onSubmit={handleSubmit} noValidate>
          <div className="login-field">
            <label htmlFor="center-id">센터 ID</label>
            <input id="center-id" name="center-id" autoComplete="username" value={centerId} onChange={(event) => setCenterId(event.target.value)} placeholder="센터 번호를 입력하세요." aria-invalid={Boolean(error)} />
          </div>
          <div className="login-field">
            <label htmlFor="password">비밀번호</label>
            <div className="password-field">
              <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" aria-invalid={Boolean(error)} />
              <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 표시'}><img src="/figma-assets/login-eye.svg" alt="" /></button>
            </div>
          </div>
          <div className="login-options">
            <label className="check-label"><input type="checkbox" checked={rememberId} onChange={(event) => setRememberId(event.target.checked)} />ID 저장</label>
            <span>비밀번호 재요청(관리자 문의)</span>
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="login-button" type="submit" disabled={submitting}>{submitting ? '확인 중…' : '로그인'}</button>
        </form>
      </section>
    </main>
  );
}
