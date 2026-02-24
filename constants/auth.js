import { createContext, useContext, useState } from 'react';

const AuthContext = createContext({ phone: '', setPhone: () => {} });

export function AuthProvider({ children }) {
  const [phone, setPhone] = useState('');
  return (
    <AuthContext.Provider value={{ phone, setPhone }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
