import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Manager from "./Manager";
import Login from "./Login";
import LoginCallback from "./LoginCallback";
import "./App.css";

/* 
  /manager is where the manager is stored.
  / probably has to ask someone to specify a domain and authenticate
  /auth/{domain} could do this with no UI

  User should be cookied when starting.
  Backend should store: cookie: {}
*/

function App() {
  //return <Manager />;

  return (
    <BrowserRouter basename={process.env.REACT_APP_BASE_PATH}>
      <Routes>
        <Route path="/manager" element={<Manager />} />
        <Route path="/login" element={<Login />} />
        <Route path="/callback" element={<LoginCallback />} />
        <Route path="/" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
