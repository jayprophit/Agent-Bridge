int main() {
    std::cout << "HELLO" << std::endl;
    return 0;
}

#include <fstream>

int main() {
    std::ofstream file("test.txt");
    file << "HELLO";
    file.close();
    return 0;
}