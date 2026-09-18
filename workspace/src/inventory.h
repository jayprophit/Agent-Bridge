#ifndef INVENTORY_H
#define INVENTORY_H

#include <string>
#include <map>

class Inventory {
public:
    void addItem(const std::string& name, int quantity);
    void removeItem(const std::string& name);
    void updateQuantity(const std::string& name, int quantity);
    int queryQuantity(const std::string& name) const;
    void listItems() const;

private:
    std::map<std::string, int> items;
};

#endif // INVENTORY_H